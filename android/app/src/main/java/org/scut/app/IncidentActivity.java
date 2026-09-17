package org.scut.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;

import org.json.JSONArray;
import org.json.JSONObject;

/** Shows only real evidence returned by the authenticated Incident endpoint. */
public class IncidentActivity extends Activity {
    private LinearLayout content;
    private String incidentId;
    private String conversationId;

    @Override protected void attachBaseContext(Context base) { super.attachBaseContext(LocaleHelper.apply(base)); }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        incidentId = getIntent().getStringExtra("incidentId");
        conversationId = getIntent().getStringExtra("conversationId");
        LinearLayout page = ScutUi.column(this);
        LinearLayout toolbar = new LinearLayout(this); toolbar.setGravity(Gravity.CENTER_VERTICAL); toolbar.setPadding(ScutUi.dp(this, 8), 0, ScutUi.dp(this, 20), 0);
        Button back = ScutUi.tertiary(this, "‹"); back.setTextSize(28); back.setGravity(Gravity.CENTER); back.setContentDescription(getString(R.string.a11y_back)); back.setOnClickListener(view -> finish()); toolbar.addView(back, new LinearLayout.LayoutParams(ScutUi.dp(this, 48), ScutUi.dp(this, 48)));
        toolbar.addView(ScutUi.text(this, getString(R.string.incident_title), 18, ScutUi.INK, Typeface.BOLD));
        page.addView(toolbar, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ScutUi.dp(this, 64)));
        content = ScutUi.column(this); content.setPadding(ScutUi.dp(this, 20), ScutUi.dp(this, 20), ScutUi.dp(this, 20), ScutUi.dp(this, 40));
        page.addView(ScutUi.scroll(this, content), new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(page);
        ScutUi.applySystemBars(this, page);
        content.addView(ScutUi.title(this, getString(R.string.state_loading)));
        if (incidentId == null || incidentId.isEmpty()) showUnavailable(); else load();
    }

    private void load() {
        CloudControl.incidentAsync(this, incidentId, (result, error) -> runOnUiThread(() -> {
            JSONObject incident = result == null ? null : result.optJSONObject("incident");
            if (incident != null) {
                CredentialStore.putPrivate(this, "incidentCache:" + incidentId, result.toString());
                showIncident(incident, false);
                return;
            }
            try {
                JSONObject cached = new JSONObject(CredentialStore.getPrivate(this, "incidentCache:" + incidentId));
                JSONObject value = cached.optJSONObject("incident"); if (value != null) showIncident(value, true); else showUnavailable();
            } catch (Exception ignored) { showUnavailable(); }
        }));
    }

    private void showIncident(JSONObject incident, boolean cached) {
        content.removeAllViews();
        String state = incident.optString("state");
        boolean cleared = "CLEARED".equals(state) || "USER_DISMISSED".equals(state);
        if (cached) content.addView(ScutUi.text(this, getString(R.string.state_offline_cached), 13, ScutUi.AMBER, Typeface.NORMAL));
        content.addView(ScutUi.label(this, ScutUi.date(this, incident.optString("created_at")) + " · " + ScutUi.time(this, incident.optString("created_at"))), ScutUi.matchWrap(this, cached ? 14 : 0));
        android.widget.TextView title = ScutUi.text(this, cleared ? getString(R.string.alert_cleared) : getString(R.string.alert_possible_scam), 30, ScutUi.INK, Typeface.BOLD);
        content.addView(title, ScutUi.matchWrap(this, 18));
        content.addView(ScutUi.text(this, supportedReason(incident), 17, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 12));
        String excerpt = evidenceExcerpt(incident.optJSONArray("incident_evidence"));
        if (!excerpt.isEmpty()) {
            LinearLayout evidence = ScutUi.section(this); evidence.addView(ScutUi.label(this, getString(R.string.conversation_evidence)));
            evidence.addView(ScutUi.text(this, excerpt, 18, ScutUi.INK, Typeface.NORMAL), ScutUi.matchWrap(this, 10));
            content.addView(evidence, ScutUi.matchWrap(this, 30));
        } else content.addView(ScutUi.text(this, getString(R.string.incident_context_limited), 14, ScutUi.MUTED, Typeface.NORMAL), ScutUi.matchWrap(this, 24));
        if ((conversationId == null || conversationId.isEmpty())) conversationId = incident.optString("session_id");
        if (conversationId != null && !conversationId.isEmpty()) {
            Button open = ScutUi.primary(this, getString(R.string.incident_open_conversation));
            open.setOnClickListener(view -> startActivity(new Intent(this, ConversationActivity.class).putExtra("conversationId", conversationId)));
            content.addView(open, ScutUi.matchWrap(this, 28));
        }
        ScutUi.animateIn(this, title, 0);
    }

    private String supportedReason(JSONObject incident) {
        String source = incident.optString("source");
        return "AUTO".equals(source) || "MERGED".equals(source) ? getString(R.string.incident_reason_known) : getString(R.string.incident_reason_generic);
    }

    private String evidenceExcerpt(JSONArray evidence) {
        if (evidence == null) return "";
        for (int index = 0; index < evidence.length(); index++) {
            JSONObject item = evidence.optJSONObject(index); JSONObject payload = item == null ? null : item.optJSONObject("payload");
            if (payload == null || payload.optBoolean("redacted", false)) continue;
            String text = payload.optString("text"); if (!text.isEmpty()) return ScutUi.ellipsize(text, 320);
        }
        return "";
    }

    private void showUnavailable() { content.removeAllViews(); content.addView(ScutUi.title(this, getString(R.string.incident_unavailable))); }
}
