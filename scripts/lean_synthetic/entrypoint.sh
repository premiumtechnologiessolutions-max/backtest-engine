#!/bin/sh
set -eu
mkdir /tmp/data
cp -R /metadata/. /tmp/data/
ln -s /fixture/forex /tmp/data/forex
exec dotnet /runner/QuantConnect.Lean.Launcher.dll --config /fixture/config.json
