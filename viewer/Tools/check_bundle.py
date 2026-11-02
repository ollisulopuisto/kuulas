"""Fail an actual native build with wrong type ownership, extension or signing.

Run only on macOS with a built app path. This is not an installer/native UI test.
"""
import plistlib
import subprocess
import sys
from pathlib import Path


def load(path):
    return plistlib.loads(path.read_bytes())


def check(app):
    app = Path(app)
    info = load(app / 'Contents/Info.plist')
    document = info['CFBundleDocumentTypes'][0]
    ownership = (document['CFBundleTypeRole'], document['LSHandlerRank'])
    if ownership != ('Viewer', 'Alternate'):
        raise RuntimeError('Viewer must not take editor ownership')
    if document['LSItemContentTypes'] != ['fi.sulopuisto.kuulas.project']:
        raise RuntimeError('Wrong Kuulas document type')
    extension = app / 'Contents/PlugIns/KuulasPreview.appex'
    preview = load(extension / 'Contents/Info.plist')['NSExtension']
    if preview['NSExtensionPointIdentifier'] != 'com.apple.quicklook.preview':
        raise RuntimeError('Missing Quick Look preview point')
    if preview['NSExtensionAttributes']['QLSupportedContentTypes'] != [
            'fi.sulopuisto.kuulas.project']:
        raise RuntimeError('Wrong preview type')
    for bundle in (extension, app):
        # Fixed executable and argument array; app path is never shell code.
        subprocess.run(  # noqa: S603
            ['/usr/bin/codesign', '--verify', '--strict', '--verbose=2', str(bundle)],
            check=True)
        result = subprocess.run(  # noqa: S603
            ['/usr/bin/codesign', '-d', '--entitlements', ':-', str(bundle)],
            check=True, capture_output=True)
        entitlements = plistlib.loads(result.stdout)
        if not entitlements.get('com.apple.security.app-sandbox'):
            raise RuntimeError('Sandbox is missing')
        if entitlements.get('com.apple.security.get-task-allow'):
            raise RuntimeError('Debug entitlement leaked into build')
        if any('temporary-exception' in key for key in entitlements):
            raise RuntimeError('Unexpected broad sandbox exception')
    print('Bundle type, embedded extension, signature and sandbox checks passed')


if __name__ == '__main__':
    check(sys.argv[1])
