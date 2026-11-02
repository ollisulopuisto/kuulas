"""Static guardrails, not evidence the native bundle builds or registers."""
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'viewer'


def plist(path):
    return plistlib.loads((ROOT / path).read_bytes())


def test_viewer_does_not_take_default_editor_ownership():
    app = plist('App/Info.plist')
    document = app['CFBundleDocumentTypes'][0]
    assert document['CFBundleTypeRole'] == 'Viewer'
    assert document['LSHandlerRank'] == 'Alternate'
    assert document['LSItemContentTypes'] == ['fi.sulopuisto.kuulas.project']
    imported = app['UTImportedTypeDeclarations'][0]['UTTypeIdentifier']
    assert imported == document['LSItemContentTypes'][0]
    assert 'UTExportedTypeDeclarations' not in app


def test_quicklook_uses_existing_package_type_and_read_only_sandbox():
    ext = plist('Extension/Info.plist')['NSExtension']
    assert ext['NSExtensionPointIdentifier'] == 'com.apple.quicklook.preview'
    assert ext['NSExtensionAttributes']['QLSupportedContentTypes'] == [
        'fi.sulopuisto.kuulas.project']
    for path in ('App/App.entitlements', 'Extension/Preview.entitlements'):
        permissions = plist(path)
        assert permissions == {'com.apple.security.app-sandbox': True,
                               'com.apple.security.files.user-selected.read-only': True}


def test_shared_view_is_used_by_host_and_extension():
    for path in ('App/AppDelegate.swift', 'Extension/PreviewViewController.swift'):
        assert 'ProjectView(root: url)' in (ROOT / path).read_text()
    project = (ROOT / 'project.yml').read_text()
    # A source plist must not be overwritten during XcodeGen generation.
    assert '\n    info:' not in project
    assert 'INFOPLIST_FILE: App/Info.plist' in project
    assert 'INFOPLIST_FILE: Extension/Info.plist' in project
