package org.scut.app;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputFilter;
import android.text.InputType;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.Space;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.DateFormat;
import java.util.Date;

public class MainActivity extends Activity implements ScutAppState.Listener {
    private static final int NOTIFICATION_REQUEST = 41;
    private static final int HOME = 0, HISTORY = 1, ALERTS = 2, SETTINGS_TAB = 3;

    private FrameLayout root;
    private FrameLayout screenSlot;
    private FrameLayout contentSlot;
    private LinearLayout shellView;
    private ScutAppState appState;
    private ScutAppState.Snapshot state;
    private int tab = HOME;
    private boolean waitingForSetupPermission;
    private String pendingIncidentId;

    @Override protected void attachBaseContext(Context base) { super.attachBaseContext(LocaleHelper.apply(base)); }

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        root = findViewById(R.id.appRoot);
        ScutUi.applySystemBars(this, root);
        screenSlot = new FrameLayout(this);
        root.addView(screenSlot, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        if (savedInstanceState != null) tab = savedInstanceState.getInt("tab", HOME);
        appState = ScutAppState.get(this);
        appState.addListener(this);
        captureIncidentTarget(getIntent());
        appState.start();
    }

    @Override protected void onResume() {
        super.onResume();
        if (appState != null && state != null && state.phase != ScutAppState.Phase.WELCOME) appState.refresh();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        captureIncidentTarget(intent);
        if (appState != null) appState.refresh();
    }

    @Override protected void onSaveInstanceState(Bundle out) { out.putInt("tab", tab); super.onSaveInstanceState(out); }
    @Override protected void onDestroy() { if (appState != null) appState.removeListener(this); super.onDestroy(); }

    @Override public void onState(ScutAppState.Snapshot next) {
        runOnUiThread(() -> {
            state = next;
            render();
            if (pendingIncidentId != null && next.phase == ScutAppState.Phase.READY && CloudControl.configured(this)) {
                String id = pendingIncidentId;
                pendingIncidentId = null;
                startActivity(new Intent(this, IncidentActivity.class).putExtra("incidentId", id));
            }
        });
    }

    private void render() {
        if (screenSlot == null || state == null) return;
        if (state.phase == ScutAppState.Phase.WELCOME) showFullScreen(welcome());
        else if (state.phase == ScutAppState.Phase.LOADING && !CloudControl.configured(this)) showFullScreen(centerState(R.string.state_loading, 0));
        else if (state.phase == ScutAppState.Phase.ERROR && !isPinError(state.error)) showFullScreen(errorState());
        else {
            ensureShell();
            contentSlot.removeAllViews();
            contentSlot.addView(content());
        }
    }

    private void showFullScreen(View page) {
        if (screenSlot.getChildAt(0) == page) return;
        screenSlot.removeAllViews();
        screenSlot.addView(page);
    }

    private void ensureShell() {
        if (shellView == null) {
            shellView = ScutUi.column(this);
            shellView.addView(topBar(), new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ScutUi.dp(this, 62)));
            contentSlot = new FrameLayout(this);
            shellView.addView(contentSlot, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
            shellView.addView(bottomNav(), new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ScutUi.dp(this, 70)));
        }
        if (screenSlot.getChildAt(0) != shellView) {
            screenSlot.removeAllViews();
            screenSlot.addView(shellView);
        }
    }

    private View welcome() {
        LinearLayout page = ScutUi.column(this);
        page.setGravity(Gravity.CENTER_VERTICAL);
        page.setPadding(ScutUi.dp(this, 28), ScutUi.dp(this, 32), ScutUi.dp(this, 28), ScutUi.dp(this, 32));
        TextView brand = ScutUi.text(this, getString(R.string.app_name), 18, ScutUi.GREEN, Typeface.BOLD);
        brand.setLetterSpacing(.18f);
        page.addView(brand);
        TextView title = ScutUi.text(this, getString(R.string.welcome_title), 34, ScutUi.INK, Typeface.BOLD);
        page.addView(title, ScutUi.matchWrap(this, 34));
        TextView body = ScutUi.text(this, getString(R.string.welcome_body), 17, ScutUi.MUTED, Typeface.NORMAL);
        page.addView(body, ScutUi.matchWrap(this, 16));
        TextView privacy = ScutUi.text(this, getString(R.string.welcome_privacy), 13, ScutUi.MUTED, Typeface.NORMAL);
        page.addView(privacy, ScutUi.matchWrap(this, 28));
        Button setup = ScutUi.primary(this, getString(R.string.welcome_action));
        setup.setOnClickListener(view -> beginSetup());
        page.addView(setup, ScutUi.matchWrap(this, 32));
        ScutUi.animateIn(this, brand, 0); ScutUi.animateIn(this, title, 70); ScutUi.animateIn(this, body, 120); ScutUi.animateIn(this, setup, 190);
        return page;
    }

    private void beginSetup() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            waitingForSetupPermission = true;
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_REQUEST);
        } else appState.beginSetup();
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == NOTIFICATION_REQUEST && waitingForSetupPermission) {
            waitingForSetupPermission = false;
            appState.beginSetup();
        }
    }

    private View topBar() {
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(ScutUi.dp(this, 20), 0, ScutUi.dp(this, 20), 0);
        bar.setBackgroundColor(ScutUi.CANVAS);
        TextView brand = ScutUi.text(this, getString(R.string.app_name), 17, ScutUi.INK, Typeface.BOLD);
        brand.setLetterSpacing(.12f);
        bar.addView(brand);
        Space space = new Space(this); bar.addView(space, new LinearLayout.LayoutParams(0, 1, 1));
        String role = state.isController() ? getString(R.string.role_primary) : getString(R.string.role_protected);
        TextView roleView = ScutUi.label(this, role);
        roleView.setTextColor(state.offline ? ScutUi.AMBER : ScutUi.MUTED);
        bar.addView(roleView);
        return bar;
    }

    private View content() {
        if (tab == HISTORY) return history();
        if (tab == ALERTS) return alerts();
        if (tab == SETTINGS_TAB) return settings();
        return home();
    }

    private View bottomNav() {
        LinearLayout nav = new LinearLayout(this);
        nav.setGravity(Gravity.CENTER);
        nav.setPadding(ScutUi.dp(this, 8), ScutUi.dp(this, 4), ScutUi.dp(this, 8), ScutUi.dp(this, 4));
        nav.setBackgroundColor(ScutUi.RAISED);
        int[] labels = {R.string.nav_home, R.string.nav_history, R.string.nav_alerts, R.string.nav_settings};
        int[] icons = {R.drawable.ic_scut_home, R.drawable.ic_scut_history, R.drawable.ic_scut_alerts, R.drawable.ic_scut_settings};
        for (int index = 0; index < labels.length; index++) {
            final int target = index;
            Button button = new Button(this);
            button.setText(labels[index]);
            button.setTextSize(11);
            button.setTextColor(index == tab ? ScutUi.GREEN : ScutUi.MUTED);
            button.setAllCaps(false);
            button.setGravity(Gravity.CENTER);
            button.setPadding(0, ScutUi.dp(this, 5), 0, ScutUi.dp(this, 3));
            button.setMinHeight(ScutUi.dp(this, 58));
            button.setStateListAnimator(null);
            button.setBackgroundColor(index == tab ? Color.argb(28, 29, 111, 73) : Color.TRANSPARENT);
            Drawable icon = getDrawable(icons[index]).mutate();
            icon.setTint(index == tab ? ScutUi.GREEN : ScutUi.MUTED);
            button.setCompoundDrawablesWithIntrinsicBounds(null, icon, null, null);
            button.setCompoundDrawablePadding(ScutUi.dp(this, 2));
            button.setOnClickListener(view -> { tab = target; render(); });
            nav.addView(button, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1));
        }
        return nav;
    }

    private View home() {
        if (state.noController() || isPinError(state.error)) return noController();
        return state.isController() ? primaryHome() : receiverHome();
    }

    private View noController() {
        LinearLayout content = pageContent();
        content.addView(ScutUi.label(this, getString(R.string.role_primary)));
        content.addView(ScutUi.title(this, getString(R.string.controller_none_title)), ScutUi.matchWrap(this, 10));
        content.addView(ScutUi.text(this, getString(R.string.controller_none_body), 16, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 12));
        EditText pin = new EditText(this);
        pin.setHint(R.string.controller_pin_hint);
        pin.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_VARIATION_PASSWORD);
        pin.setFilters(new InputFilter[]{new InputFilter.LengthFilter(4)});
        pin.setTextSize(22); pin.setLetterSpacing(.22f); pin.setSingleLine(true);
        pin.setPadding(ScutUi.dp(this, 16), 0, ScutUi.dp(this, 16), 0);
        pin.setBackground(ScutUi.background(ScutUi.RAISED, ScutUi.dp(this, 14), ScutUi.dp(this, 1), ScutUi.STONE));
        content.addView(pin, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ScutUi.dp(this, 58)) {{ topMargin = ScutUi.dp(MainActivity.this, 28); }});
        if (isPinError(state.error)) {
            TextView error = ScutUi.text(this, pinErrorMessage(state.error), 14, ScutUi.RUST, Typeface.NORMAL);
            content.addView(error, ScutUi.matchWrap(this, 10));
        }
        Button claim = ScutUi.primary(this, getString(R.string.controller_claim));
        claim.setOnClickListener(view -> { String value = pin.getText().toString(); pin.setText(""); if (value.length() == 4) appState.claim(value); });
        content.addView(claim, ScutUi.matchWrap(this, 18));
        content.addView(ScutUi.text(this, getString(R.string.controller_pin_help), 13, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 16));
        return ScutUi.scroll(this, content);
    }

    private View primaryHome() {
        LinearLayout content = pageContent();
        statusLockup(content, R.string.state_ready, R.string.role_primary, ScutUi.GREEN);
        JSONObject protectedPhone = state.role.optJSONObject("protectedPhone");
        LinearLayout receiver = ScutUi.section(this);
        receiver.addView(ScutUi.label(this, getString(R.string.home_protected_phone)));
        String name = protectedPhone == null ? getString(R.string.home_no_phone) : protectedPhone.optString("displayName", getString(R.string.role_protected));
        receiver.addView(ScutUi.text(this, name, 18, ScutUi.INK, Typeface.BOLD), ScutUi.matchWrap(this, 7));
        if (protectedPhone == null) receiver.addView(ScutUi.text(this, getString(R.string.home_no_phone_body), 14, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 7));
        Button choose = ScutUi.tertiary(this, getString(R.string.home_choose_phone));
        choose.setOnClickListener(view -> showReceiverPicker());
        receiver.addView(choose, ScutUi.matchWrap(this, 10));
        content.addView(receiver, ScutUi.matchWrap(this, 32));

        LinearLayout controls = ScutUi.column(this);
        controls.setBackgroundColor(ScutUi.CANVAS);
        LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout copy = ScutUi.column(this); copy.setBackgroundColor(Color.TRANSPARENT);
        copy.addView(ScutUi.text(this, getString(R.string.home_volume_controls), 17, ScutUi.INK, Typeface.BOLD));
        copy.addView(ScutUi.text(this, getString(R.string.home_volume_controls_body), 13, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 4));
        row.addView(copy, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Switch toggle = new Switch(this); toggle.setChecked(state.controlsEnabled()); toggle.setContentDescription(getString(R.string.home_volume_controls));
        toggle.setOnCheckedChangeListener((button, checked) -> {
            String active = state.role.optString("activeReceiverId", "");
            if (active.isEmpty()) { button.setChecked(false); showReceiverPicker(); }
            else appState.selectReceiver(active, checked);
        });
        row.addView(toggle, new LinearLayout.LayoutParams(ScutUi.dp(this, 56), ScutUi.dp(this, 56)));
        controls.addView(row);
        content.addView(controls, ScutUi.matchWrap(this, 26));
        addRecentConversation(content);
        return ScutUi.scroll(this, content);
    }

    private View receiverHome() {
        LinearLayout content = pageContent();
        boolean active = state.isActiveReceiver();
        statusLockup(content, active ? R.string.state_protection_connected : R.string.state_waiting_selection, R.string.role_protected, active ? ScutUi.GREEN : ScutUi.AMBER);
        TextView body = ScutUi.text(this, active ? getString(R.string.home_pc_connection) : getString(R.string.state_waiting_selection_body), 16, ScutUi.MUTED, Typeface.NORMAL);
        content.addView(body, ScutUi.matchWrap(this, 18));
        if (!notificationsGranted()) content.addView(permissionIssue(R.string.settings_notifications, R.string.permission_notifications_body, this::openNotificationSettings), ScutUi.matchWrap(this, 28));
        addRecentConversation(content);
        return ScutUi.scroll(this, content);
    }

    private void statusLockup(LinearLayout content, int title, int role, int tone) {
        LinearLayout line = new LinearLayout(this); line.setGravity(Gravity.CENTER_VERTICAL);
        TextView dot = ScutUi.text(this, "•", 24, tone, Typeface.BOLD);
        line.addView(dot); line.addView(ScutUi.label(this, getString(role)), ScutUi.matchWrap(this, 0));
        content.addView(line);
        TextView heading = ScutUi.text(this, getString(title), 32, ScutUi.INK, Typeface.BOLD);
        content.addView(heading, ScutUi.matchWrap(this, 12));
        ScutUi.animateIn(this, heading, 20);
        if (state.offline) content.addView(ScutUi.text(this, getString(R.string.state_offline_cached), 13, ScutUi.AMBER, Typeface.NORMAL), ScutUi.matchWrap(this, 12));
    }

    private void addRecentConversation(LinearLayout content) {
        content.addView(ScutUi.divider(this), ScutUi.dividerParams(this, 30));
        content.addView(ScutUi.label(this, getString(R.string.home_recent_event)), ScutUi.matchWrap(this, 20));
        JSONObject recent = state.conversations.optJSONObject(0);
        if (recent == null) content.addView(ScutUi.text(this, getString(R.string.home_no_recent_event), 17, ScutUi.INK, Typeface.BOLD), ScutUi.matchWrap(this, 8));
        else {
            TextView preview = ScutUi.text(this, ScutUi.ellipsize(recent.optString("preview"), 140), 17, ScutUi.INK, Typeface.NORMAL);
            preview.setPadding(0, ScutUi.dp(this, 8), 0, ScutUi.dp(this, 16));
            preview.setOnClickListener(view -> openConversation(recent.optString("id")));
            content.addView(preview);
        }
    }

    private View history() {
        LinearLayout content = pageContent();
        pageHeading(content, R.string.history_title, R.string.history_subtitle);
        if (state.offline) content.addView(ScutUi.text(this, getString(R.string.state_offline_cached), 13, ScutUi.AMBER, Typeface.NORMAL), ScutUi.matchWrap(this, 12));
        if (state.conversations.length() == 0) return emptyList(content, R.string.history_empty, R.string.history_empty_body);
        String previousDate = "";
        for (int index = 0; index < state.conversations.length(); index++) {
            JSONObject item = state.conversations.optJSONObject(index); if (item == null) continue;
            String date = ScutUi.date(this, item.optString("startedAt"));
            if (!date.equals(previousDate)) { content.addView(ScutUi.label(this, date), ScutUi.matchWrap(this, index == 0 ? 28 : 24)); previousDate = date; }
            View row = conversationRow(item); content.addView(row); content.addView(ScutUi.divider(this));
            if (index < 6) ScutUi.animateIn(this, row, index * 38L);
        }
        if (appState.hasMoreHistory()) {
            Button more = ScutUi.tertiary(this, getString(R.string.action_load_more));
            more.setOnClickListener(view -> { more.setEnabled(false); more.setText(R.string.state_loading); appState.loadMoreHistory(); });
            content.addView(more, ScutUi.matchWrap(this, 18));
        }
        return ScutUi.scroll(this, content);
    }

    private View conversationRow(JSONObject item) {
        LinearLayout row = new LinearLayout(this); row.setOrientation(LinearLayout.VERTICAL); row.setMinimumHeight(ScutUi.dp(this, 72));
        row.setPadding(0, ScutUi.dp(this, 14), 0, ScutUi.dp(this, 14)); row.setBackgroundColor(ScutUi.CANVAS);
        LinearLayout meta = new LinearLayout(this); meta.setGravity(Gravity.CENTER_VERTICAL);
        meta.addView(ScutUi.text(this, ScutUi.time(this, item.optString("startedAt")), 13, ScutUi.MUTED, Typeface.NORMAL));
        Space space = new Space(this); meta.addView(space, new LinearLayout.LayoutParams(0, 1, 1));
        long seconds = item.optLong("durationSeconds", 0); String duration = seconds < 60 ? getString(R.string.history_duration_seconds, seconds) : getString(R.string.history_duration_minutes, Math.max(1, seconds / 60));
        int tone = "incident".equals(item.optString("attentionState")) ? ScutUi.RUST : "cleared".equals(item.optString("attentionState")) ? ScutUi.MUTED : ScutUi.GREEN;
        TextView durationView = ScutUi.text(this, duration, 13, tone, Typeface.NORMAL); meta.addView(durationView);
        row.addView(meta);
        String preview = item.optString("preview");
        row.addView(ScutUi.text(this, preview.isEmpty() ? getString(R.string.conversation_no_transcript) : ScutUi.ellipsize(preview, 160), 16, ScutUi.INK, Typeface.NORMAL), ScutUi.matchWrap(this, 7));
        row.setOnClickListener(view -> openConversation(item.optString("id")));
        return row;
    }

    private View alerts() {
        LinearLayout content = pageContent();
        pageHeading(content, R.string.alerts_title, R.string.alerts_subtitle);
        if (state.offline) content.addView(ScutUi.text(this, getString(R.string.state_offline_cached), 13, ScutUi.AMBER, Typeface.NORMAL), ScutUi.matchWrap(this, 12));
        if (state.alerts.length() == 0) return emptyList(content, R.string.alerts_empty, R.string.alerts_empty_body);
        for (int index = 0; index < state.alerts.length(); index++) {
            JSONObject item = state.alerts.optJSONObject(index); if (item == null) continue;
            String incidentState = item.optString("state"); boolean cleared = "CLEARED".equals(incidentState) || "USER_DISMISSED".equals(incidentState);
            LinearLayout row = ScutUi.column(this); row.setBackgroundColor(ScutUi.CANVAS); row.setPadding(0, ScutUi.dp(this, 16), 0, ScutUi.dp(this, 16));
            row.addView(ScutUi.text(this, cleared ? getString(R.string.alert_cleared) : getString(R.string.alert_possible_scam), 17, cleared ? ScutUi.MUTED : ScutUi.INK, Typeface.BOLD));
            String preview = item.optString("conversationPreview");
            row.addView(ScutUi.text(this, preview.isEmpty() ? getString(R.string.incident_context_limited) : ScutUi.ellipsize(preview, 150), 14, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 6));
            row.addView(ScutUi.label(this, ScutUi.time(this, item.optString("updatedAt"))), ScutUi.matchWrap(this, 8));
            row.setOnClickListener(view -> startActivity(new Intent(this, IncidentActivity.class).putExtra("incidentId", item.optString("id")).putExtra("conversationId", item.optString("conversationId"))));
            content.addView(row); content.addView(ScutUi.divider(this));
            if (index < 6) ScutUi.animateIn(this, row, index * 38L);
        }
        if (appState.hasMoreAlerts()) {
            Button more = ScutUi.tertiary(this, getString(R.string.action_load_more));
            more.setOnClickListener(view -> { more.setEnabled(false); more.setText(R.string.state_loading); appState.loadMoreAlerts(); });
            content.addView(more, ScutUi.matchWrap(this, 18));
        }
        return ScutUi.scroll(this, content);
    }

    private View settings() {
        LinearLayout content = pageContent(); pageHeading(content, R.string.settings_title, state.isController() ? R.string.role_primary : R.string.role_protected);
        content.addView(sectionLabel(R.string.settings_language), ScutUi.matchWrap(this, 28));
        content.addView(settingRow(R.string.settings_language, currentLanguageLabel(), this::showLanguagePicker));
        content.addView(sectionLabel(R.string.settings_permissions), ScutUi.matchWrap(this, 28));
        content.addView(settingRow(R.string.settings_notifications, notificationsGranted() ? getString(R.string.settings_on) : getString(R.string.settings_off), this::openNotificationSettings));
        if (state.isController()) content.addView(settingRow(R.string.settings_accessibility, accessibilityEnabled() ? getString(R.string.settings_on) : getString(R.string.settings_off), () -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))));
        else content.addView(settingRow(R.string.settings_overlay, Settings.canDrawOverlays(this) ? getString(R.string.settings_on) : getString(R.string.settings_optional), () -> startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())))));
        content.addView(sectionLabel(R.string.settings_privacy), ScutUi.matchWrap(this, 28));
        TextView privacy = ScutUi.text(this, getString(R.string.settings_privacy_body), 15, ScutUi.MUTED, Typeface.NORMAL); content.addView(privacy, ScutUi.matchWrap(this, 10));
        content.addView(sectionLabel(R.string.settings_phone_role), ScutUi.matchWrap(this, 28));
        content.addView(settingRow(state.isController() ? R.string.role_primary : R.string.role_protected, state.offline ? getString(R.string.state_needs_attention) : getString(R.string.settings_on), null));
        if (state.isController()) {
            Button release = ScutUi.tertiary(this, getString(R.string.controller_release)); release.setTextColor(ScutUi.RUST); release.setOnClickListener(view -> confirmRelease()); content.addView(release, ScutUi.matchWrap(this, 8));
        }
        content.addView(sectionLabel(R.string.settings_advanced), ScutUi.matchWrap(this, 28));
        content.addView(settingRow(R.string.settings_advanced, "", () -> startActivity(new Intent(this, AdvancedActivity.class))));
        return ScutUi.scroll(this, content);
    }

    private TextView sectionLabel(int text) { TextView label = ScutUi.label(this, getString(text)); label.setTextColor(ScutUi.GREEN); label.setTypeface(Typeface.DEFAULT_BOLD); return label; }

    private View settingRow(int title, String value, Runnable action) {
        LinearLayout row = new LinearLayout(this); row.setGravity(Gravity.CENTER_VERTICAL); row.setMinimumHeight(ScutUi.dp(this, 58)); row.setBackgroundColor(ScutUi.CANVAS);
        row.addView(ScutUi.text(this, getString(title), 16, ScutUi.INK, Typeface.NORMAL), new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        if (!value.isEmpty()) row.addView(ScutUi.text(this, value, 14, ScutUi.MUTED, Typeface.NORMAL));
        if (action != null) { row.setClickable(true); row.setOnClickListener(view -> action.run()); }
        return row;
    }

    private View permissionIssue(int title, int body, Runnable action) {
        LinearLayout section = ScutUi.section(this); section.addView(ScutUi.text(this, getString(title), 17, ScutUi.INK, Typeface.BOLD)); section.addView(ScutUi.text(this, getString(body), 14, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 6));
        Button fix = ScutUi.tertiary(this, getString(R.string.action_fix)); fix.setOnClickListener(view -> action.run()); section.addView(fix, ScutUi.matchWrap(this, 8)); return section;
    }

    private View emptyList(LinearLayout content, int title, int body) {
        content.addView(ScutUi.text(this, getString(title), 22, ScutUi.INK, Typeface.BOLD), ScutUi.matchWrap(this, 70));
        content.addView(ScutUi.text(this, getString(body), 15, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 10));
        return ScutUi.scroll(this, content);
    }

    private LinearLayout pageContent() { LinearLayout content = ScutUi.column(this); content.setPadding(ScutUi.dp(this, 20), ScutUi.dp(this, 18), ScutUi.dp(this, 20), ScutUi.dp(this, 36)); return content; }
    private void pageHeading(LinearLayout content, int title, int subtitle) { content.addView(ScutUi.title(this, getString(title))); content.addView(ScutUi.text(this, getString(subtitle), 14, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 7)); }

    private void showReceiverPicker() {
        JSONArray receivers = state.receivers;
        if (receivers.length() == 0) { new AlertDialog.Builder(this).setTitle(R.string.home_no_phone).setMessage(R.string.home_no_phone_body).setPositiveButton(R.string.action_close, null).show(); return; }
        String[] labels = new String[receivers.length()]; int checked = -1; String active = state.role.optString("activeReceiverId", "");
        for (int index = 0; index < receivers.length(); index++) { JSONObject receiver = receivers.optJSONObject(index); labels[index] = receiver == null ? getString(R.string.role_protected) : receiver.optString("displayName", getString(R.string.role_protected)); if (receiver != null && receiver.optString("id").equals(active)) checked = index; }
        new AlertDialog.Builder(this).setTitle(R.string.receiver_sheet_title).setSingleChoiceItems(labels, checked, (dialog, which) -> {
            JSONObject receiver = receivers.optJSONObject(which); if (receiver != null) { root.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK); appState.selectReceiver(receiver.optString("id"), state.controlsEnabled()); }
            dialog.dismiss();
        }).setNegativeButton(R.string.action_cancel, null).show();
    }

    private void confirmRelease() {
        new AlertDialog.Builder(this).setTitle(R.string.controller_release).setMessage(R.string.controller_release_confirm).setNegativeButton(R.string.action_cancel, null)
                .setPositiveButton(R.string.controller_release_action, (dialog, which) -> { root.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK); appState.release(); }).show();
    }

    private void showLanguagePicker() {
        String[] labels = {getString(R.string.settings_system_language), getString(R.string.settings_russian), getString(R.string.settings_romanian), getString(R.string.settings_english)};
        String[] values = {"system", "ru", "ro", "en"}; String current = getSharedPreferences("scut", MODE_PRIVATE).getString("language", "system"); int checked = 0;
        for (int i = 0; i < values.length; i++) if (values[i].equals(current)) checked = i;
        new AlertDialog.Builder(this).setTitle(R.string.settings_language).setSingleChoiceItems(labels, checked, (dialog, which) -> { LocaleHelper.save(this, values[which]); dialog.dismiss(); recreate(); }).setNegativeButton(R.string.action_cancel, null).show();
    }

    private String currentLanguageLabel() {
        String value = getSharedPreferences("scut", MODE_PRIVATE).getString("language", "system");
        if ("ru".equals(value)) return getString(R.string.settings_russian); if ("ro".equals(value)) return getString(R.string.settings_romanian); if ("en".equals(value)) return getString(R.string.settings_english); return getString(R.string.settings_system_language);
    }

    private boolean notificationsGranted() { return Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED; }
    private void openNotificationSettings() { if (Build.VERSION.SDK_INT >= 33 && !notificationsGranted()) requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATION_REQUEST); else startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName())); }
    private boolean accessibilityEnabled() { AccessibilityManager manager = (AccessibilityManager) getSystemService(ACCESSIBILITY_SERVICE); if (manager == null) return false; for (android.accessibilityservice.AccessibilityServiceInfo service : manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)) if (service.getResolveInfo().serviceInfo.packageName.equals(getPackageName())) return true; return false; }

    private View errorState() {
        LinearLayout page = pageContent(); page.setGravity(Gravity.CENTER_VERTICAL); page.addView(ScutUi.title(this, getString(R.string.state_needs_attention))); page.addView(ScutUi.text(this, getString(R.string.welcome_offline), 16, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 12)); Button retry = ScutUi.primary(this, getString(R.string.action_retry)); retry.setOnClickListener(view -> appState.refresh()); page.addView(retry, ScutUi.matchWrap(this, 26)); return page;
    }

    private View centerState(int title, int body) { LinearLayout page = pageContent(); page.setGravity(Gravity.CENTER); page.addView(ScutUi.title(this, getString(title))); if (body != 0) page.addView(ScutUi.text(this, getString(body), 15, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 10)); return page; }
    private boolean isPinError(String error) { return "MASTER_PASSWORD_REQUIRED".equals(error) || "CONTROLLER_ALREADY_CLAIMED".equals(error) || "ENROLLMENT_RATE_LIMITED".equals(error) || "CONTROLLER_CLAIM_FAILED".equals(error); }
    private String pinErrorMessage(String error) { if ("CONTROLLER_ALREADY_CLAIMED".equals(error)) return getString(R.string.controller_race_lost); if ("ENROLLMENT_RATE_LIMITED".equals(error)) return getString(R.string.controller_rate_limited); return getString(R.string.controller_wrong_pin); }
    private void openConversation(String id) { if (!id.isEmpty()) startActivity(new Intent(this, ConversationActivity.class).putExtra("conversationId", id)); }

    private void captureIncidentTarget(Intent intent) {
        if (intent == null) return;
        String id = intent.getStringExtra("incidentId");
        Uri data = intent.getData();
        if ((id == null || id.isEmpty()) && data != null && "incident".equals(data.getHost()) && data.getPathSegments().size() == 1) id = data.getPathSegments().get(0);
        if (id != null && !id.isEmpty()) pendingIncidentId = id;
    }
}
