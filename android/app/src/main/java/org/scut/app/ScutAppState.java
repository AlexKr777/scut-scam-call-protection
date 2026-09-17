package org.scut.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

/** Single authority for cloud role, sync, receiver, history and alert presentation state. */
public final class ScutAppState {
    public enum Phase { WELCOME, LOADING, READY, ERROR }
    public interface Listener { void onState(Snapshot state); }

    public static final class Snapshot {
        public final Phase phase;
        public final JSONObject role;
        public final JSONArray conversations;
        public final JSONArray alerts;
        public final JSONArray receivers;
        public final boolean offline;
        public final String error;
        public final long lastSyncMillis;

        Snapshot(Phase phase, JSONObject role, JSONArray conversations, JSONArray alerts, JSONArray receivers,
                 boolean offline, String error, long lastSyncMillis) {
            this.phase = phase;
            this.role = role;
            this.conversations = conversations;
            this.alerts = alerts;
            this.receivers = receivers;
            this.offline = offline;
            this.error = error;
            this.lastSyncMillis = lastSyncMillis;
        }

        public boolean isController() { return role.optBoolean("isController", false); }
        public boolean noController() { return "NO_CONTROLLER".equals(role.optString("state")); }
        public boolean isActiveReceiver() { return role.optBoolean("isActiveReceiver", false); }
        public boolean controlsEnabled() { return role.optBoolean("hardwareControlsEnabled", false); }
    }

    private static ScutAppState instance;
    private final Context context;
    private final SharedPreferences preferences;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final CopyOnWriteArrayList<Listener> listeners = new CopyOnWriteArrayList<>();
    private Snapshot snapshot;
    private String historyCursor;
    private String alertsCursor;

    private ScutAppState(Context context) {
        this.context = context.getApplicationContext();
        preferences = this.context.getSharedPreferences("scut", Context.MODE_PRIVATE);
        snapshot = new Snapshot(
                shouldWelcome() ? Phase.WELCOME : Phase.LOADING,
                fallbackRole(),
                cachedArray("historyCache", "conversations"),
                cachedArray("alertsCache", "alerts"),
                new JSONArray(),
                false,
                null,
                CloudControl.lastSyncMillis(context));
    }

    public static synchronized ScutAppState get(Context context) {
        if (instance == null) instance = new ScutAppState(context);
        return instance;
    }

    public Snapshot current() { return snapshot; }
    public boolean hasMoreHistory() { return historyCursor != null && !historyCursor.isEmpty(); }
    public boolean hasMoreAlerts() { return alertsCursor != null && !alertsCursor.isEmpty(); }
    public void addListener(Listener listener) { listeners.addIfAbsent(listener); listener.onState(snapshot); }
    public void removeListener(Listener listener) { listeners.remove(listener); }

    public void start() {
        if (shouldWelcome()) {
            update(new Snapshot(Phase.WELCOME, snapshot.role, snapshot.conversations, snapshot.alerts,
                    snapshot.receivers, false, null, snapshot.lastSyncMillis));
        } else {
            main.post(this::refresh);
        }
    }

    public void beginSetup() {
        preferences.edit().putBoolean("onboardingStarted", true).apply();
        loading();
        CloudControl.ensureEnrolledAsync(context, (result, error) -> {
            if (error != null) {
                fail(error);
                return;
            }
            preferences.edit().putBoolean("onboardingComplete", true).apply();
            CloudControl.refreshFcmToken(context);
            refresh();
        });
    }

    public void refresh() {
        if (!CloudControl.configured(context)) {
            if (preferences.getBoolean("onboardingStarted", false)) beginSetup();
            else update(new Snapshot(Phase.WELCOME, fallbackRole(), snapshot.conversations, snapshot.alerts,
                    new JSONArray(), false, null, snapshot.lastSyncMillis));
            return;
        }
        loading();
        CloudControl.controllerStateAsync(context, (result, error) -> main.post(() -> {
            if (result == null) {
                offline(error == null ? "CONTROLLER_STATE_UNAVAILABLE" : error);
                return;
            }
            update(new Snapshot(Phase.READY, result, snapshot.conversations, snapshot.alerts,
                    snapshot.receivers, false, null, CloudControl.lastSyncMillis(context)));
            refreshContent();
            if (result.optBoolean("isController", false)) refreshReceivers();
        }));
    }

    public void claim(String pin) {
        loading();
        CloudControl.claimControllerAsync(context, pin, (result, error) -> main.post(() -> {
            if (result == null) fail(error == null ? "CONTROLLER_CLAIM_FAILED" : error);
            else refresh();
        }));
    }

    public void release() {
        loading();
        CloudControl.releaseControllerAsync(context, (result, error) -> main.post(() -> {
            if (result == null) fail(error == null ? "CONTROLLER_RELEASE_FAILED" : error);
            else refresh();
        }));
    }

    public void selectReceiver(String receiverId, boolean controlsEnabled) {
        CloudControl.configureSystemAsync(context, receiverId, controlsEnabled, (result, error) -> main.post(() -> {
            if (result == null) fail(error == null ? "SYSTEM_CONFIGURATION_FAILED" : error);
            else refresh();
        }));
    }

    private void refreshContent() {
        CloudControl.historyAsync(context, (result, error) -> main.post(() -> {
            if (result != null) {
                historyCursor = result.optString("nextCursor", "");
                CredentialStore.putPrivate(context, "historyCache", result.toString());
                update(new Snapshot(snapshot.phase, snapshot.role, result.optJSONArray("conversations") == null ? new JSONArray() : result.optJSONArray("conversations"),
                        snapshot.alerts, snapshot.receivers, snapshot.offline, snapshot.error, snapshot.lastSyncMillis));
            } else if (snapshot.conversations.length() == 0) offline(error);
        }));
        CloudControl.alertsAsync(context, (result, error) -> main.post(() -> {
            if (result != null) {
                alertsCursor = result.optString("nextCursor", "");
                CredentialStore.putPrivate(context, "alertsCache", result.toString());
                update(new Snapshot(snapshot.phase, snapshot.role, snapshot.conversations,
                        result.optJSONArray("alerts") == null ? new JSONArray() : result.optJSONArray("alerts"),
                        snapshot.receivers, snapshot.offline, snapshot.error, snapshot.lastSyncMillis));
            } else if (snapshot.alerts.length() == 0) offline(error);
        }));
    }

    public void loadMoreHistory() {
        String cursor = historyCursor;
        if (cursor == null || cursor.isEmpty()) return;
        historyCursor = null;
        CloudControl.historyAsync(context, cursor, (result, error) -> main.post(() -> {
            if (result == null) {
                historyCursor = cursor;
                update(new Snapshot(snapshot.phase, snapshot.role, snapshot.conversations, snapshot.alerts,
                        snapshot.receivers, true, error, snapshot.lastSyncMillis));
                return;
            }
            JSONArray conversations = appendUnique(snapshot.conversations, result.optJSONArray("conversations"));
            historyCursor = result.optString("nextCursor", "");
            CredentialStore.putPrivate(context, "historyCache", cachedPage("conversations", conversations, historyCursor).toString());
            update(new Snapshot(snapshot.phase, snapshot.role, conversations, snapshot.alerts,
                    snapshot.receivers, false, null, snapshot.lastSyncMillis));
        }));
    }

    public void loadMoreAlerts() {
        String cursor = alertsCursor;
        if (cursor == null || cursor.isEmpty()) return;
        alertsCursor = null;
        CloudControl.alertsAsync(context, cursor, (result, error) -> main.post(() -> {
            if (result == null) {
                alertsCursor = cursor;
                update(new Snapshot(snapshot.phase, snapshot.role, snapshot.conversations, snapshot.alerts,
                        snapshot.receivers, true, error, snapshot.lastSyncMillis));
                return;
            }
            JSONArray alerts = appendUnique(snapshot.alerts, result.optJSONArray("alerts"));
            alertsCursor = result.optString("nextCursor", "");
            CredentialStore.putPrivate(context, "alertsCache", cachedPage("alerts", alerts, alertsCursor).toString());
            update(new Snapshot(snapshot.phase, snapshot.role, snapshot.conversations, alerts,
                    snapshot.receivers, false, null, snapshot.lastSyncMillis));
        }));
    }

    private void refreshReceivers() {
        CloudControl.receiversAsync(context, (result, error) -> main.post(() -> {
            if (result == null) return;
            JSONObject role = copy(snapshot.role);
            try {
                role.put("activeReceiverId", result.optString("activeReceiverId", ""));
                role.put("hardwareControlsEnabled", result.optBoolean("hardwareControlsEnabled", false));
            } catch (Exception ignored) { }
            update(new Snapshot(snapshot.phase, role, snapshot.conversations, snapshot.alerts,
                    result.optJSONArray("receivers") == null ? new JSONArray() : result.optJSONArray("receivers"),
                    snapshot.offline, snapshot.error, snapshot.lastSyncMillis));
        }));
    }

    private boolean shouldWelcome() {
        return !preferences.getBoolean("onboardingComplete", false) && !CloudControl.configured(context);
    }

    private void loading() {
        update(new Snapshot(Phase.LOADING, snapshot.role, snapshot.conversations, snapshot.alerts,
                snapshot.receivers, snapshot.offline, null, snapshot.lastSyncMillis));
    }

    private void fail(String error) {
        main.post(() -> update(new Snapshot(Phase.ERROR, snapshot.role, snapshot.conversations, snapshot.alerts,
                snapshot.receivers, snapshot.offline, error, snapshot.lastSyncMillis)));
    }

    private void offline(String error) {
        update(new Snapshot(Phase.READY, fallbackRole(), snapshot.conversations, snapshot.alerts,
                snapshot.receivers, true, error, CloudControl.lastSyncMillis(context)));
    }

    private void update(Snapshot state) {
        snapshot = state;
        for (Listener listener : listeners) listener.onState(state);
    }

    private JSONObject fallbackRole() {
        JSONObject role = new JSONObject();
        try {
            boolean controller = "CONTROLLER".equals(CloudControl.role(context));
            role.put("state", "ASSIGNMENT_UNKNOWN");
            role.put("role", controller ? "CONTROLLER" : "RECEIVER");
            role.put("isController", controller);
            role.put("hardwareControlsEnabled", controller && CloudControl.controllerButtonsEnabled(context));
        } catch (Exception ignored) { }
        return role;
    }

    private JSONArray cachedArray(String key, String arrayKey) {
        try {
            JSONObject cached = new JSONObject(CredentialStore.getPrivate(context, key));
            JSONArray array = cached.optJSONArray(arrayKey);
            return array == null ? new JSONArray() : array;
        } catch (Exception ignored) {
            return new JSONArray();
        }
    }

    private static JSONObject copy(JSONObject source) {
        try { return new JSONObject(source.toString()); } catch (Exception ignored) { return new JSONObject(); }
    }

    private static JSONArray appendUnique(JSONArray current, JSONArray page) {
        JSONArray merged = new JSONArray();
        Set<String> ids = new HashSet<>();
        for (int index = 0; index < current.length(); index++) {
            JSONObject item = current.optJSONObject(index);
            if (item != null) { merged.put(item); ids.add(item.optString("id")); }
        }
        if (page != null) for (int index = 0; index < page.length(); index++) {
            JSONObject item = page.optJSONObject(index);
            if (item != null && ids.add(item.optString("id"))) merged.put(item);
        }
        return merged;
    }

    private static JSONObject cachedPage(String key, JSONArray items, String cursor) {
        JSONObject value = new JSONObject();
        try { value.put(key, items).put("nextCursor", cursor == null ? "" : cursor); } catch (Exception ignored) { }
        return value;
    }
}
