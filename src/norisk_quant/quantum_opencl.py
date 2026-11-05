"""Optional single-precision QAOA statevector on explicitly selected OpenCL devices."""
from __future__ import annotations

import importlib.util
import math
import re

import numpy as np


OPENCL_BACKENDS = {'opencl': 'gpu', 'opencl-cpu': 'cpu'}
_SELECTOR = re.compile(r'(?:0|[1-9][0-9]{0,3}):(?:0|[1-9][0-9]{0,3})')
_DEVICE_VERSION = re.compile(r'OpenCL (\d+)\.(\d+)')
_NORM_TOLERANCE = 2e-5


class OpenCLUnavailable(RuntimeError):
    """The requested OpenCL runtime or device cannot execute this circuit."""


def validate_opencl_selector(selector):
    if selector is not None and (type(selector) is not str or not _SELECTOR.fullmatch(selector)):
        raise ValueError('OpenCL device selector must be platform_index:device_index')
    return selector


def _scan():
    if importlib.util.find_spec('pyopencl') is None:
        return None, [], 'PACKAGE_MISSING'
    try:
        import pyopencl as cl
    except (ImportError, OSError):
        return None, [], 'IMPORT_FAILED'
    try:
        platforms = cl.get_platforms()
    except cl.Error:
        return cl, [], 'PLATFORM_UNAVAILABLE'

    devices = []
    failed_query = False
    for platform_index, platform in enumerate(platforms):
        try:
            platform_devices = platform.get_devices()
        except cl.Error:
            failed_query = True
            continue
        for device_index, device in enumerate(platform_devices):
            try:
                if device.type & cl.device_type.GPU:
                    kind = 'gpu'
                elif device.type & cl.device_type.CPU:
                    kind = 'cpu'
                else:
                    continue
                version = _DEVICE_VERSION.match(device.version)
                compatible = bool(device.available and device.compiler_available and version
                                  and tuple(map(int, version.groups())) >= (1, 2))
                details = {
                    'selector': f'{platform_index}:{device_index}',
                    'device_type': kind,
                    'platform_name': platform.name,
                    'platform_vendor': platform.vendor,
                    'device_name': device.name,
                    'device_vendor': device.vendor,
                    'driver_version': device.driver_version,
                    'device_version': device.version,
                    'compatible': compatible,
                }
                devices.append((details, device))
            except cl.Error:
                failed_query = True
    if devices:
        return cl, devices, 'DEVICE_DISCOVERED'
    return cl, [], 'DEVICE_QUERY_FAILED' if failed_query else 'NO_CPU_OR_GPU_DEVICE'


def opencl_capabilities():
    _, devices, status = _scan()
    capabilities = {}
    for backend, kind in OPENCL_BACKENDS.items():
        matched = [info for info, _ in devices if info['device_type'] == kind]
        available = any(info['compatible'] for info in matched)
        capabilities[backend] = {
            'installed': status != 'PACKAGE_MISSING',
            'available': available,
            'status': ('DEVICE_AVAILABLE' if available else 'NO_COMPATIBLE_DEVICE')
                      if status == 'DEVICE_DISCOVERED' else status,
            'devices': matched,
            'execution_verified': False,
            'precision': 'float32',
        }
    return capabilities


def _select(backend, selector):
    validate_opencl_selector(selector)
    kind = OPENCL_BACKENDS[backend]
    cl, devices, status = _scan()
    for info, device in devices:
        if (info['device_type'] == kind and info['compatible']
                and (selector is None or selector == info['selector'])):
            return cl, device, info
    if status == 'PACKAGE_MISSING':
        raise OpenCLUnavailable('Install the optional gpu extra to use OpenCL')
    if status == 'DEVICE_DISCOVERED':
        status = 'NO_COMPATIBLE_DEVICE'
    raise OpenCLUnavailable(f'No compatible OpenCL {kind.upper()} for this selection ({status})')


def opencl_device_identity(backend, device=None):
    """Return the actual platform/driver metadata used to bind a queued job."""
    return _select(backend, device)[2]


_KERNELS = r'''
__kernel void initialize(__global float2 *state, float amplitude)
{
    state[get_global_id(0)] = (float2)(amplitude, 0.0f);
}

__kernel void apply_phase(__global float2 *state, __global const float *energy,
                          float gamma)
{
    uint i = get_global_id(0);
    float angle = gamma * energy[i];
    float c = cos(angle);
    float s = sin(angle);
    float2 a = state[i];
    state[i] = (float2)(c * a.x + s * a.y, c * a.y - s * a.x);
}

__kernel void apply_mixer(__global float2 *state, uint bit, float c, float s)
{
    uint pair = get_global_id(0);
    uint stride = 1u << bit;
    uint first = ((pair >> bit) << (bit + 1u)) | (pair & (stride - 1u));
    uint second = first | stride;
    float2 a = state[first];
    float2 b = state[second];
    state[first] = (float2)(c * a.x + s * b.y, c * a.y - s * b.x);
    state[second] = (float2)(c * b.x + s * a.y, c * b.y - s * a.x);
}

__kernel void measure(__global const float2 *state, __global float *probabilities)
{
    uint i = get_global_id(0);
    float2 a = state[i];
    probabilities[i] = dot(a, a);
}
'''


class OpenCLStatevector:
    """Keep the kernels, energy table and buffers resident for one angle search."""

    def __init__(self, energies, backend, device=None):
        cl, selected, self.device = _select(backend, device)
        self.cl = cl
        self.size = len(energies)
        self.qubits = self.size.bit_length() - 1
        self.energy_scale = max(1., float(np.max(np.abs(energies))))
        energy = np.asarray(energies / self.energy_scale, dtype=np.float32)
        self.host_probabilities = np.empty_like(energy)
        try:
            self.context = cl.Context(devices=[selected],
                                      properties=[(cl.context_properties.PLATFORM, selected.platform)])
            self.queue = cl.CommandQueue(self.context, device=selected)
            self.program = cl.Program(self.context, _KERNELS).build(options=['-cl-std=CL1.2'])
            self.initialize = self.program.initialize
            self.apply_phase = self.program.apply_phase
            self.apply_mixer = self.program.apply_mixer
            self.measure = self.program.measure
            flags = cl.mem_flags
            self.energy_buffer = cl.Buffer(self.context, flags.READ_ONLY | flags.COPY_HOST_PTR,
                                           hostbuf=energy)
            self.state_buffer = cl.Buffer(self.context, flags.READ_WRITE, 2 * energy.nbytes)
            self.probability_buffer = cl.Buffer(self.context, flags.WRITE_ONLY, energy.nbytes)
        except cl.Error as exc:
            raise OpenCLUnavailable('OpenCL context, kernel build or buffer allocation failed') from exc

    def probabilities(self, parameters):
        # Limit phase argument error in the FP32 cost kernel. The solver uses
        # normalized energies and angles in [-pi, pi], well within this range.
        scaled = [(gamma * self.energy_scale, beta) for gamma, beta in parameters]
        if any(not math.isfinite(gamma) or abs(gamma) > 32. for gamma, _ in scaled):
            raise ValueError('OpenCL FP32 cost phase must be at most 32 radians')
        cl = self.cl
        try:
            self.initialize(self.queue, (self.size,), None, self.state_buffer,
                            np.float32(1. / math.sqrt(self.size)))
            for gamma, beta in scaled:
                self.apply_phase(self.queue, (self.size,), None, self.state_buffer,
                                 self.energy_buffer, np.float32(gamma))
                c, s = np.float32(math.cos(beta)), np.float32(math.sin(beta))
                for bit in range(self.qubits):
                    self.apply_mixer(self.queue, (self.size // 2,), None,
                                     self.state_buffer, np.uint32(bit), c, s)
            self.measure(self.queue, (self.size,), None, self.state_buffer,
                         self.probability_buffer)
            cl.enqueue_copy(self.queue, self.host_probabilities, self.probability_buffer,
                            is_blocking=True)
        except cl.Error as exc:
            raise OpenCLUnavailable('OpenCL statevector execution failed') from exc
        probabilities = self.host_probabilities.astype(float)
        total = float(probabilities.sum())
        if (not np.isfinite(probabilities).all() or (probabilities < 0.).any()
                or abs(total - 1.) > _NORM_TOLERANCE):
            raise OpenCLUnavailable('OpenCL returned an invalid probability distribution')
        return probabilities / total
