package org.scut.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.MenuItem;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

public class ConversationActivity extends Activity {
    private LinearLayout content;
    private String conversationId;

    @Override protected void attachBaseContext(Context base) { super.attachBaseContext(LocaleHelper.apply(base)); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        conversationId = getIntent().getStringExtra("conversationId");
        if (conversationId == null) conversationId = "";
        LinearLayout page = ScutUi.column(this);
        page.addView(toolbar(), new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ScutUi.dp(this, 64)));
        content = ScutUi.column(this);
        content.setPadding(ScutUi.dp(this, 20), ScutUi.dp(this, 18), ScutUi.dp(this, 20), ScutUi.dp(this, 42));
        page.addView(ScutUi.scroll(this, content), new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(page);
        ScutUi.applySystemBars(this, page);
        showLoading();
        load();
    }

    private View toolbar() {
        LinearLayout bar = new LinearLayout(this); bar.setGravity(Gravity.CENTER_VERTICAL); bar.setPadding(ScutUi.dp(this, 8), 0, ScutUi.dp(this, 8), 0); bar.setBackgroundColor(ScutUi.CANVAS);
        Button back = ScutUi.tertiary(this, "‹"); back.setContentDescription(getString(R.string.a11y_back)); back.setTextSize(28); back.setGravity(Gravity.CENTER); back.setOnClickListener(view -> finish()); bar.addView(back, new LinearLayout.LayoutParams(ScutUi.dp(this, 48), ScutUi.dp(this, 48)));
        TextView title = ScutUi.text(this, getString(R.string.conversation_title), 18, ScutUi.INK, Typeface.BOLD); bar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button more = ScutUi.tertiary(this, "⋯"); more.setContentDescription(getString(R.string.a11y_more)); more.setTextSize(24); more.setGravity(Gravity.CENTER); more.setOnClickListener(this::showMenu); bar.addView(more, new LinearLayout.LayoutParams(ScutUi.dp(this, 48), ScutUi.dp(this, 48)));
        return bar;
    }

    private void showMenu(View anchor) {
        PopupMenu menu = new PopupMenu(this, anchor); menu.getMenu().add(getString(R.string.history_delete));
        menu.setOnMenuItemClickListener(item -> { confirmDelete(); return true; }); menu.show();
    }

    private void showLoading() { content.removeAllViews(); content.addView(ScutUi.title(this, getString(R.string.state_loading))); }

    private void load() {
        CloudControl.conversationAsync(this, conversationId, (result, error) -> runOnUiThread(() -> {
            if (result != null && result.optJSONObject("conversation") != null) {
                CredentialStore.putPrivate(this, "conversationCache:" + conversationId, result.toString());
                showConversation(result.optJSONObject("conversation"), false);
                return;
            }
            try {
                JSONObject cached = new JSONObject(CredentialStore.getPrivate(this, "conversationCache:" + conversationId));
                JSONObject conversation = cached.optJSONObject("conversation");
                if (conversation != null) showConversation(conversation, true); else showUnavailable();
            } catch (Exception ignored) { showUnavailable(); }
        }));
    }

    private void showConversation(JSONObject conversation, boolean cached) {
        content.removeAllViews();
        if (cached) content.addView(ScutUi.text(this, getString(R.string.state_offline_cached), 13, ScutUi.AMBER, Typeface.NORMAL));
        content.addView(ScutUi.label(this, ScutUi.date(this, conversation.optString("startedAt")) + " · " + ScutUi.time(this, conversation.optString("startedAt"))), ScutUi.matchWrap(this, cached ? 14 : 0));
        String device = conversation.optString("protectedReceiverName");
        if (!device.isEmpty()) content.addView(ScutUi.text(this, device, 15, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 7));
        content.addView(ScutUi.title(this, getString(R.string.conversation_transcript)), ScutUi.matchWrap(this, 28));
        JSONArray segments = conversation.optJSONArray("segments");
        if (segments == null || segments.length() == 0) content.addView(ScutUi.text(this, getString(R.string.conversation_no_transcript), 16, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 20));
        else for (int index = 0; index < segments.length(); index++) {
            JSONObject segment = segments.optJSONObject(index); if (segment == null) continue;
            LinearLayout row = ScutUi.column(this); row.setBackgroundColor(ScutUi.CANVAS); row.setPadding(0, ScutUi.dp(this, 18), 0, ScutUi.dp(this, 18));
            row.addView(ScutUi.label(this, ScutUi.time(this, segment.optString("ended_at"))));
            row.addView(ScutUi.text(this, segment.optString("text"), 18, ScutUi.INK, Typeface.NORMAL), ScutUi.matchWrap(this, 7));
            content.addView(row); content.addView(ScutUi.divider(this));
        }
        JSONArray incidents = conversation.optJSONArray("incidents");
        if (incidents != null && incidents.length() > 0) {
            JSONObject incident = incidents.optJSONObject(0);
            LinearLayout warning = ScutUi.section(this); warning.addView(ScutUi.label(this, getString(R.string.conversation_evidence)));
            boolean cleared = incident != null && ("CLEARED".equals(incident.optString("state")) || "USER_DISMISSED".equals(incident.optString("state")));
            warning.addView(ScutUi.text(this, cleared ? getString(R.string.alert_cleared) : getString(R.string.alert_possible_scam), 18, cleared ? ScutUi.MUTED : ScutUi.RUST, Typeface.BOLD), ScutUi.matchWrap(this, 7));
            if (incident != null) warning.setOnClickListener(view -> startActivity(new android.content.Intent(this, IncidentActivity.class).putExtra("incidentId", incident.optString("id")).putExtra("conversationId", conversationId)));
            content.addView(warning, ScutUi.matchWrap(this, 28));
        }
    }

    private void showUnavailable() { content.removeAllViews(); content.addView(ScutUi.title(this, getString(R.string.history_deleted_remote))); }

    private void confirmDelete() {
        new AlertDialog.Builder(this).setTitle(R.string.history_delete).setMessage(R.string.history_delete_confirm).setNegativeButton(R.string.action_cancel, null)
                .setPositiveButton(R.string.action_delete, (dialog, which) -> CloudControl.deleteConversationAsync(this, conversationId, (result, error) -> runOnUiThread(() -> {
                    if (result != null && result.optBoolean("deleted", false)) {
                        CredentialStore.removePrivate(this, "conversationCache:" + conversationId);
                        content.performHapticFeedback(android.view.HapticFeedbackConstants.CLOCK_TICK); finish();
                    } else showUnavailable();
                }))).show();
    }
}
