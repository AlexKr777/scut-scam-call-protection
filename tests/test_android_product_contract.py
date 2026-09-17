import unittest
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android" / "app" / "src" / "main"


class AndroidProductContractTests(unittest.TestCase):
    def _string_names(self, directory: str) -> set[str]:
        root = ElementTree.parse(ANDROID / "res" / directory / "strings.xml").getroot()
        return {node.attrib["name"] for node in root.findall("string")}

    def test_ru_ro_and_en_catalogs_have_identical_keys(self):
        english = self._string_names("values")
        self.assertGreaterEqual(len(english), 100)
        self.assertEqual(english, self._string_names("values-ru"))
        self.assertEqual(english, self._string_names("values-ro"))

    def test_manifest_exposes_only_safe_product_entry_points(self):
        manifest = (ANDROID / "AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:scheme="scut" android:host="incident"', manifest)
        self.assertIn('android:name=".ConversationActivity" android:exported="false"', manifest)
        self.assertIn('android:name=".AdvancedActivity" android:exported="false"', manifest)
        self.assertNotIn('android:allowBackup="true"', manifest)

    def test_normal_ui_has_no_developer_configuration_fields(self):
        normal_ui = "\n".join(
            (ANDROID / "java" / "org" / "scut" / "app" / name).read_text(encoding="utf-8")
            for name in ("MainActivity.java", "ConversationActivity.java", "IncidentActivity.java")
        )
        for forbidden in ("cloudEndpoint", "masterPassword", "cloudDeviceId", "pairToken"):
            self.assertNotIn(forbidden, normal_ui)

    def test_device_credential_is_keystore_backed_and_not_logged(self):
        credential_store = (ANDROID / "java" / "org" / "scut" / "app" / "CredentialStore.java").read_text(encoding="utf-8")
        cloud_control = (ANDROID / "java" / "org" / "scut" / "app" / "CloudControl.java").read_text(encoding="utf-8")
        local_service = (ANDROID / "java" / "org" / "scut" / "app" / "ScutService.java").read_text(encoding="utf-8")
        self.assertIn("AndroidKeyStore", credential_store)
        self.assertIn("AES/GCM/NoPadding", credential_store)
        self.assertIn("getLocal", credential_store)
        self.assertIn("putLocal", credential_store)
        self.assertIn("putPrivate", credential_store)
        self.assertNotIn('putString("credential"', local_service)
        self.assertNotIn('putString("pairToken"', local_service)
        self.assertNotIn("Log.", credential_store + cloud_control)
        self.assertNotIn('"1321"', credential_store + cloud_control)

    def test_dividers_keep_a_fixed_one_dp_height(self):
        main_activity = (ANDROID / "java" / "org" / "scut" / "app" / "MainActivity.java").read_text(encoding="utf-8")
        self.assertNotIn("addView(ScutUi.divider(this), ScutUi.matchWrap", main_activity)

    def test_state_updates_keep_the_main_shell_in_place(self):
        main_activity = (ANDROID / "java" / "org" / "scut" / "app" / "MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("ensureShell();", main_activity)
        self.assertIn("contentSlot.removeAllViews();", main_activity)
        self.assertNotIn("root.removeAllViews();", main_activity)
        self.assertNotIn("beginDelayedTransition(root", main_activity)

    def test_history_and_alerts_expose_real_cursor_pagination(self):
        source_root = ANDROID / "java" / "org" / "scut" / "app"
        cloud_control = (source_root / "CloudControl.java").read_text(encoding="utf-8")
        app_state = (source_root / "ScutAppState.java").read_text(encoding="utf-8")
        main_activity = (source_root / "MainActivity.java").read_text(encoding="utf-8")
        self.assertIn("historyAsync(Context context, String cursor", cloud_control)
        self.assertIn("alertsAsync(Context context, String cursor", cloud_control)
        self.assertIn("loadMoreHistory()", app_state)
        self.assertIn("loadMoreAlerts()", app_state)
        self.assertIn("R.string.action_load_more", main_activity)

    def test_system_language_restores_the_platform_locale(self):
        locale_helper = (ANDROID / "java" / "org" / "scut" / "app" / "LocaleHelper.java").read_text(encoding="utf-8")
        self.assertIn("Resources.getSystem()", locale_helper)
        self.assertNotIn('if (language == null || "system".equals(language)) return context;', locale_helper)

    def test_transcript_and_incident_caches_are_keystore_encrypted(self):
        source_root = ANDROID / "java" / "org" / "scut" / "app"
        sources = "\n".join(
            (source_root / name).read_text(encoding="utf-8")
            for name in ("ScutAppState.java", "ConversationActivity.java", "IncidentActivity.java")
        )
        for forbidden in ('putString("historyCache"', 'putString("alertsCache"', 'putString("conversationCache:', 'putString("incidentCache:'):
            self.assertNotIn(forbidden, sources)
        self.assertIn("CredentialStore.putPrivate", sources)

    def test_every_product_activity_applies_system_bar_insets(self):
        source_root = ANDROID / "java" / "org" / "scut" / "app"
        for name in ("MainActivity.java", "ConversationActivity.java", "IncidentActivity.java", "AdvancedActivity.java"):
            source = (source_root / name).read_text(encoding="utf-8")
            self.assertIn("ScutUi.applySystemBars", source, name)

    def test_advanced_pairing_advertises_only_the_supported_local_socket_scheme(self):
        source = (ANDROID / "java" / "org" / "scut" / "app" / "AdvancedActivity.java").read_text(encoding="utf-8")
        self.assertIn('startsWith("ws://")', source)
        self.assertNotIn('startsWith("wss://")', source)


if __name__ == "__main__":
    unittest.main()
