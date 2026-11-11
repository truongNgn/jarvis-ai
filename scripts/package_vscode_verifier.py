"""Build the tiny first-party verifier VSIX without Node, npm or downloads."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
output = root / '.local' / 'workspace-verifier.vsix'
output.parent.mkdir(exist_ok=True)
manifest = '''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
<Metadata><Identity Language="en-US" Id="workspace-verifier" Version="0.1.4" Publisher="jarvis-ai"/>
<DisplayName>JARVIS Workspace Verifier</DisplayName><Description xml:space="preserve">Local workspace evidence.</Description></Metadata>
<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
<Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets>
</PackageManifest>'''
types = '''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/>
<Default Extension="vsixmanifest" ContentType="text/xml"/></Types>'''
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    archive.writestr('extension.vsixmanifest', manifest)
    archive.writestr('[Content_Types].xml', types)
    for name in ('package.json', 'extension.js'):
        archive.write(root / 'integrations' / 'vscode-verifier' / name, 'extension/' + name)
print(output)
