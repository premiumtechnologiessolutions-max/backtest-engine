FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /source
COPY lean/ .
COPY NrfxSyntheticAlgorithm.cs Algorithm.CSharp/
RUN dotnet publish Launcher/QuantConnect.Lean.Launcher.csproj -c Release -o /runner -p:RunAnalyzers=false -p:EnableNETAnalyzers=false

FROM mcr.microsoft.com/dotnet/runtime:10.0
ARG LEAN_COMMIT
LABEL org.opencontainers.image.source="https://github.com/QuantConnect/Lean" \
      org.opencontainers.image.revision="$LEAN_COMMIT" \
      org.noriskfx.contract="NRFX_LEAN_SYNTHETIC_RUNTIME_V1"
COPY --from=build /runner /runner
COPY lean/Data/market-hours/market-hours-database.json /metadata/market-hours/market-hours-database.json
COPY lean/Data/symbol-properties/symbol-properties-database.csv /metadata/symbol-properties/symbol-properties-database.csv
COPY entrypoint.sh /nrfx-entrypoint.sh
USER 65532:65532
ENTRYPOINT ["/bin/sh", "/nrfx-entrypoint.sh"]
