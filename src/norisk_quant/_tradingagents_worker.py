"""Process entry point for the official pinned TradingAgents LangGraph workflow."""
from __future__ import annotations

from dataclasses import replace
from datetime import date
import hashlib
from http.client import HTTPConnection
from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys

PIN = '9fa1196fffbcfd9de5146d2dd2869df84ab99838'
SYMBOL = 'SIM_NRFX'
_UPSTREAM = 'https://github.com/TauricResearch/TradingAgents.git'
_BLOBS = {
    '__init__.py': 'e1c4209189a35c4745cf6752a4a57e326f916e1f',
    'graph/setup.py': '7cb53be0cb5db90e705c762473b428ac16f1395d',
    'graph/propagation.py': 'a4b58343e66d870a0d3bb6b3998788b20c5abc89',
    'graph/conditional_logic.py': '2c6caca2cb0c75fb280916de531eb1f466a0955d',
    'graph/analyst_execution.py': '3a4d0f70b30809c2d742624bcffc7236e20a7d57',
    'agents/analysts/market_analyst.py': '3a95df7e8a4b51e1fbfaf83e43e7813d896a2d6a',
    'agents/analysts/turn.py': '3b568b22d01fa458976df508339451e148a14dd3',
    'agents/researchers/bull_researcher.py': 'a671d1360a1ab8ed450b0a89058511cd6f51b009',
    'agents/researchers/bear_researcher.py': 'd483e893df15647f9b4e8ef4492d8f6ffe407540',
    'agents/managers/research_manager.py': '3bf288c60b6602a449f303fac7d27cb4b174cf61',
    'agents/trader/trader.py': '8993095ec368e548d1aeb1014ebb0020a009904f',
    'agents/risk_mgmt/aggressive_debator.py': '4d977dc782e6bd4e03c5acb6f8ff83c019260e1b',
    'agents/risk_mgmt/conservative_debator.py': 'e8207a890edeabb23438e3a7abda6012e8f39583',
    'agents/risk_mgmt/neutral_debator.py': '9abd0415796c00ad1b8fc78cd314314d0b10bfc0',
    'agents/managers/portfolio_manager.py': '0537b5e80e319295ab2554c7e5c0ac832341e480',
    'agents/schemas.py': 'be561f2c467ab2e414f8b2c9bf206fbb2653efbc',
    'agents/rating.py': '83f48084dcc43e5c5c18c30c6533bcb411f79a11',
    'llm_clients/openai_client.py': 'c23a2beceab156b79c45a2609c157225e47826a1',
}
GRAPH_NODES = ('Market Analyst', 'Bull Researcher', 'Bear Researcher', 'Research Manager',
               'Trader', 'Aggressive Analyst', 'Conservative Analyst', 'Neutral Analyst',
               'Portfolio Manager')
_LOCAL = ('127.0.0.1', 11434)


def _json(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _attest():
    from packaging.version import Version

    dist = metadata.distribution('tradingagents')
    source = json.loads(dist.read_text('direct_url.json') or '{}')
    vcs = source.get('vcs_info', {})
    if source.get('url') != _UPSTREAM or vcs.get('vcs') != 'git' or vcs.get('commit_id') != PIN:
        raise RuntimeError('TradingAgents must be installed from the fixed GitHub revision')
    installed = {str(path): path for path in dist.files or ()}
    digest = hashlib.sha256()
    for filename, expected in _BLOBS.items():
        path = installed.get('tradingagents/' + filename)
        if path is None:
            raise RuntimeError('Required pinned upstream source file is absent')
        with Path(dist.locate_file(path)).open('rb') as stream:
            raw = stream.read(128 * 1024).replace(b'\r\n', b'\n')
        header = f'blob {len(raw)}\0'.encode()
        if hashlib.sha1(header + raw, usedforsecurity=False).hexdigest() != expected:
            raise RuntimeError('Pinned upstream source blob does not match')
        digest.update(filename.encode() + b'\0' + hashlib.sha256(raw).digest())
    versions = {name: metadata.version(name) for name in ('langgraph', 'langchain-core', 'pandas')}
    if Version(versions['pandas']) < Version('3.0.6'):
        raise RuntimeError('TradingAgents requires its own pandas>=3.0.6 environment')
    return {'upstream_commit': PIN, 'upstream_source_sha256': digest.hexdigest(),
            'package_version': dist.version, 'isolated_runtime_versions': versions}


def _install_guard(mode):
    def guard(event, args):
        if event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'}:
            raise PermissionError('Nested process execution is disabled')
        if event == 'socket.connect':
            if mode != 'ollama' or args[1] != _LOCAL:
                raise PermissionError('Network access is disabled outside the fixed loopback model')
        elif event == 'socket.getaddrinfo':
            if mode != 'ollama' or args[:2] != _LOCAL:
                raise PermissionError('DNS lookups are disabled')
        elif event in {'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo',
                       'socket.sendto', 'socket.bind'}:
            raise PermissionError('Network operation is disabled')
        elif event == 'open' and isinstance(args[0], (str, bytes)):
            if Path(os.fsdecode(args[0])).name.startswith('.env'):
                raise PermissionError('External dotenv files are disabled')

    sys.addaudithook(guard)


def _ollama_request(method, endpoint, payload=None):
    connection = HTTPConnection(*_LOCAL, timeout=3)
    try:
        connection.request(method, endpoint, None if payload is None else _json(payload),
                           {'Content-Type': 'application/json'})
        response = connection.getresponse()
        raw = response.read(524289)
        if response.status != 200 or len(raw) > 524288:
            raise RuntimeError('Local Ollama model metadata is unavailable')
        return json.loads(raw)
    finally:
        connection.close()


def _ollama_identity(model):
    tags = _ollama_request('GET', '/api/tags')
    found = next((row for row in tags['models'] if row.get('name') == model), None)
    if (found is None or not re.fullmatch(r'[a-f0-9]{64}', found.get('digest', ''))
            or found.get('size', 0) <= 0 or found.get('details', {}).get('format') != 'gguf'):
        raise RuntimeError('Configured Ollama model is not an installed local GGUF')
    shown = _ollama_request('POST', '/api/show', {'model': model})
    if (any(item.get('remote_model') or item.get('remote_host') for item in (shown, found))
            or 'tools' not in shown.get('capabilities', [])):
        raise RuntimeError('Configured Ollama model must support local tool calling')
    return {'ollama_model': model, 'ollama_model_sha256': found['digest']}


def _market_tools(rows, fixture_id, trace):
    from langchain_core.tools import tool

    last = rows[-1]['date']

    def selected(start, end):
        if date.fromisoformat(start) > date.fromisoformat(end):
            return []
        return [row for row in rows if start <= row['date'] <= min(end, last)]

    def report(name, result, available):
        if available:
            trace.append(name)
        return _json({'provenance': 'SYNTHETIC_NOT_MARKET', 'symbol': SYMBOL,
                      'fixture_sha256': fixture_id, **result})

    @tool
    def get_stock_data(start_date: str, end_date: str) -> str:
        """Read invented fixture OHLCV sessions for the requested ISO date interval."""
        sessions = selected(start_date, end_date)
        return report('get_stock_data', {'sessions': sessions}, bool(sessions))

    @tool
    def get_indicators(indicator: str, curr_date: str, look_back_days: int = 24) -> str:
        """Read close_10_ema or atr for invented sessions at or before the given ISO date."""
        available = selected(rows[0]['date'], curr_date)[-max(1, min(24, look_back_days)):]
        value = None
        if available and indicator == 'close_10_ema':
            value = available[0]['close']
            for row in available[1:]:
                value += (row['close'] - value) * 2 / 11
        elif len(available) >= 2 and indicator == 'atr':
            ranges = [max(row['high'] - row['low'], abs(row['high'] - prior['close']),
                          abs(row['low'] - prior['close'])) for prior, row in zip(available, available[1:])]
            value = sum(ranges[-14:]) / len(ranges[-14:])
        return report('get_indicators', {'indicator': indicator[:40], 'value': value,
                                         'sessions': len(available)}, value is not None)

    @tool
    def get_verified_market_snapshot(curr_date: str, look_back_days: int = 24) -> str:
        """Read the latest invented OHLCV row and recent closes at or before an ISO date."""
        available = selected(rows[0]['date'], curr_date)[-max(1, min(24, look_back_days)):]
        return report('get_verified_market_snapshot', {'latest': available[-1] if available else None,
                                                        'closes': [row['close'] for row in available]}, bool(available))

    return get_stock_data, get_indicators, get_verified_market_snapshot


def _fixture_llm(rows, fixture_id, calls):
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.runnables import RunnableLambda

    structured = {
        'ResearchPlan': {'recommendation': 'Hold', 'rationale': 'Fixture debate remains balanced.',
                         'strategic_actions': 'Keep fictional exposure unchanged.'},
        'TraderProposal': {'action': 'Hold', 'reasoning': 'The fixture research plan asks for no trade.'},
        'PortfolioDecision': {'rating': 'Hold', 'executive_summary': 'Hold fictional exposure.',
                              'investment_thesis': 'Fixture risk debate has no verified market edge.'},
    }

    class FixtureLLM(RunnableLambda):
        def __init__(self):
            super().__init__(self.reply)

        def reply(self, _prompt):
            calls.append('fixture_debate_reply')
            return AIMessage(content='Fixture argument. Invented history cannot verify a market outcome.')

        def with_structured_output(self, schema):
            def provide(_prompt):
                calls.append(schema.__name__)
                return schema.model_validate(structured[schema.__name__])

            return RunnableLambda(provide)

        def bind_tools(self, tools):
            names = {item.name for item in tools}
            if names != {'get_stock_data', 'get_indicators', 'get_verified_market_snapshot'}:
                raise RuntimeError('Unexpected tool registry reached fixture model')

            def market(prompt):
                replies = [item for item in prompt.to_messages() if isinstance(item, ToolMessage)]
                if replies:
                    snapshot = next(item for item in replies if item.name == 'get_verified_market_snapshot')
                    observed = json.loads(snapshot.content)
                    if observed.get('fixture_sha256') != fixture_id or observed['latest'] != rows[-1]:
                        raise RuntimeError('Native ToolNode did not pass the invented snapshot')
                    calls.append('fixture_market_report')
                    return AIMessage(content=f"Invented snapshot ends {observed['latest']['date']} at "
                                             f"{observed['latest']['close']}. Fixture {fixture_id}.")
                calls.append('fixture_tool_request')
                start, end = rows[0]['date'], rows[-1]['date']
                return AIMessage(content='', tool_calls=[
                    {'name': 'get_stock_data', 'args': {'start_date': start, 'end_date': end}, 'id': 'fixture_ohlcv'},
                    {'name': 'get_verified_market_snapshot', 'args': {'curr_date': end}, 'id': 'fixture_snapshot'},
                ])

            return RunnableLambda(market)

    return FixtureLLM()


def _ollama_llm(model, calls):
    import httpx
    from langchain_core.callbacks import BaseCallbackHandler
    from tradingagents.llm_clients.factory import create_llm_client

    class CountModelCalls(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs):
            calls.append('local_model_reply')

    return create_llm_client('ollama', model, base_url='http://127.0.0.1:11434/v1',
        max_tokens=480, timeout=20, max_retries=0, temperature=0., callbacks=[CountModelCalls()],
        http_client=httpx.Client(trust_env=False, follow_redirects=False)).get_llm()


def _run(payload, identity):
    from tradingagents.agents import context, tools as upstream_tools
    from tradingagents.agents.analysts import market_analyst
    from tradingagents.agents.rating import RATINGS_5_TIER, RATING_REVIEW, run_rating
    from tradingagents.graph import ConditionalLogic, GraphSetup, Propagator, analyst_execution

    rows = payload['sessions']
    fixture_id = payload['fixture_sha256']
    if len(rows) != 24 or not re.fullmatch(r'[a-f0-9]{64}', fixture_id):
        raise ValueError('Invalid lab fixture')
    tools_run, model_calls = [], []
    tools = _market_tools(rows, fixture_id, tools_run)

    def reject_external_source(*_args, **_kwargs):
        raise PermissionError('External TradingAgents data providers are disabled')

    # Replace only the provider boundary inside the isolated process. Upstream
    # graph topology, prompt nodes, tool routing, schemas and ratings run as-is.
    upstream_tools.route_to_vendor = reject_external_source
    upstream_tools.build_verified_market_snapshot = reject_external_source
    context.get_company_profile = reject_external_source
    market_analyst.TOOLS = tools
    spec = analyst_execution.ANALYST_NODE_SPECS['market']
    analyst_execution.ANALYST_NODE_SPECS['market'] = replace(spec, tools=tools)
    mode = payload['mode']
    llm = (_fixture_llm(rows, fixture_id, model_calls) if mode == 'fixture'
           else _ollama_llm(payload['model'], model_calls))
    graph = GraphSetup(llm, llm, ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1),
                       max_tool_rounds=2).setup_graph(selected_analysts=('market',)).compile()
    state = Propagator().create_initial_state(SYMBOL, rows[-1]['date'],
        instrument_context='SIM_NRFX is invented. Use only its fixture tools and describe only fictional evidence.',
        portfolio_context='Invented portfolio with zero open positions. No order routing is enabled.')
    nodes, final = [], {}
    for update in graph.stream(state, config={'recursion_limit': 32}, stream_mode='updates'):
        for name, values in update.items():
            nodes.append(name)
            final.update(values)
    if tuple(nodes) != GRAPH_NODES or not {'get_stock_data', 'get_verified_market_snapshot'} <= set(tools_run):
        raise RuntimeError('TradingAgents did not complete the native nodes and required fixture tools')
    rating = run_rating(final)
    reports = {name: final[name] for name in ('market_report', 'investment_plan',
               'trader_investment_plan', 'final_trade_decision')}
    if (rating not in (*RATINGS_5_TIER, RATING_REVIEW) or not model_calls
            or any(not isinstance(report, str) or not report.strip() for report in reports.values())):
        raise RuntimeError('Native TradingAgents decision or reports are incomplete')
    if mode == 'ollama' and _ollama_identity(payload['model']) != {
            key: identity[key] for key in ('ollama_model', 'ollama_model_sha256')}:
        raise RuntimeError('Local Ollama model identity changed during graph execution')
    return {**identity, 'mode': mode, 'fixture_sha256': fixture_id, 'official_graph_executed': True,
            'model_inference_executed': mode == 'ollama', 'model_response_count': len(model_calls),
            'model_provider': 'fixed_fixture_responses' if mode == 'fixture' else 'ollama_loopback',
            'analysts_enabled': ['market'], 'executed_nodes': nodes,
            'fixture_tools_executed': sorted(set(tools_run)), 'fixture_tool_call_count': len(tools_run),
            'final_rating': rating, 'reports': {key: value[:3000] for key, value in reports.items()}}


def _main():
    raw = sys.stdin.buffer.read(32769)
    if not 0 < len(raw) <= 32768:
        raise ValueError('Invalid bounded worker request')
    payload = json.loads(raw)
    mode = payload['mode']
    if mode not in ('fixture', 'ollama') or len(sys.argv) != 2 or sys.argv[1] not in ('probe', 'run'):
        raise ValueError('Invalid TradingAgents worker action')
    _install_guard(mode)
    identity = _attest()
    if mode == 'ollama':
        identity.update(_ollama_identity(payload['model']))
    print(_json(identity if sys.argv[1] == 'probe' else _run(payload, identity)))


if __name__ == '__main__':
    _main()
