package org.scut.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

import com.google.firebase.messaging.FirebaseMessaging;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.Locale;

/** Authenticated Edge-Function client. Privileged credentials never enter the APK. */
public final class CloudControl {
    public interface Callback { void complete(JSONObject result, String errorCode); }

    static final String CLOUD_ENDPOINT = "https://hbmhjyjlwhmjzmenvraa.supabase.co";
    private CloudControl() { }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences("scut", Context.MODE_PRIVATE);
    }

    public static boolean configured(Context context) { return !CredentialStore.get(context).isEmpty(); }

    public static boolean controllerButtonsEnabled(Context context) {
        SharedPreferences preferences = prefs(context);
        return configured(context)
                && "CONTROLLER".equals(preferences.getString("cloudRole", ""))
                && preferences.getBoolean("hardwareControlsEnabled", false);
    }

    public static String role(Context context) { return prefs(context).getString("cloudRole", ""); }
    public static String deviceId(Context context) { return prefs(context).getString("cloudDeviceId", ""); }
    public static long lastSyncMillis(Context context) { return prefs(context).getLong("lastCloudSync", 0L); }
    public static boolean fcmRegistered(Context context) { return prefs(context).getBoolean("fcmRegistered", false); }

    /** Fresh installs safely enter the Receiver-eligible path before role authority is fetched. */
    public static void ensureEnrolledAsync(Context context, Callback callback) {
        if (configured(context)) {
            callback.complete(new JSONObject(), null);
            return;
        }
        new Thread(() -> {
            try {
                JSONObject body = new JSONObject()
                        .put("installId", installId(context))
                        .put("displayName", friendlyDeviceName())
                        .put("appVersion", appVersion(context))
                        .put("role", "RECEIVER");
                JSONObject response = post(CLOUD_ENDPOINT, "enroll-device", body, null);
                if (!CredentialStore.put(context, response.getString("credential"))) {
                    callback.complete(null, "SECURE_STORAGE_UNAVAILABLE");
                    return;
                }
                prefs(context).edit()
                        .putString("cloudDeviceId", response.getString("deviceId"))
                        .putString("cloudRole", response.optString("role", "RECEIVER"))
                        .putBoolean("hardwareControlsEnabled", false)
                        .remove("cloudEndpoint")
                        .apply();
                callback.complete(response, null);
            } catch (CloudException error) {
                callback.complete(null, error.code);
            } catch (Exception ignored) {
                callback.complete(null, "ENROLLMENT_FAILED");
            }
        }, "scut-auto-enroll").start();
    }

    public static void controllerStateAsync(Context context, Callback callback) {
        request(context, "controller-state", new JSONObject(), "CONTROLLER_STATE_UNAVAILABLE", (result, error) -> {
            if (result != null) {
                prefs(context).edit()
                        .putString("cloudRole", result.optString("role", "RECEIVER"))
                        .putBoolean("hardwareControlsEnabled", result.optBoolean("hardwareControlsEnabled", false) && result.optBoolean("isController", false))
                        .putLong("lastCloudSync", System.currentTimeMillis())
                        .apply();
            }
            callback.complete(result, error);
        });
    }

    public static void claimControllerAsync(Context context, String pin, Callback callback) {
        request(context, "claim-controller", json("masterPassword", pin), "CONTROLLER_CLAIM_FAILED", (result, error) -> {
            if (result != null) prefs(context).edit().putString("cloudRole", "CONTROLLER").putBoolean("hardwareControlsEnabled", false).apply();
            callback.complete(result, error);
        });
    }

    public static void releaseControllerAsync(Context context, Callback callback) {
        request(context, "release-controller", new JSONObject(), "CONTROLLER_RELEASE_FAILED", (result, error) -> {
            if (result != null) prefs(context).edit().putString("cloudRole", "RECEIVER").putBoolean("hardwareControlsEnabled", false).apply();
            callback.complete(result, error);
        });
    }

    public static void receiversAsync(Context context, Callback callback) {
        request(context, "receivers-list", new JSONObject(), "RECEIVERS_UNAVAILABLE", callback);
    }

    public static void configureSystemAsync(Context context, String receiverId, boolean enabled, Callback callback) {
        JSONObject body = new JSONObject();
        try { body.put("activeReceiverId", receiverId).put("hardwareControlsEnabled", enabled); } catch (Exception ignored) { }
        request(context, "configure-system", body, "SYSTEM_CONFIGURATION_FAILED", (result, error) -> {
            if (result != null) prefs(context).edit().putBoolean("hardwareControlsEnabled", result.optBoolean("hardwareControlsEnabled", false)).apply();
            callback.complete(result, error);
        });
    }

    public static void historyAsync(Context context, Callback callback) { historyAsync(context, null, callback); }
    public static void historyAsync(Context context, String cursor, Callback callback) {
        request(context, "history-list", page(cursor), "HISTORY_UNAVAILABLE", callback);
    }
    public static void alertsAsync(Context context, Callback callback) { alertsAsync(context, null, callback); }
    public static void alertsAsync(Context context, String cursor, Callback callback) {
        request(context, "alerts-list", page(cursor), "ALERTS_UNAVAILABLE", callback);
    }
    public static void conversationAsync(Context context, String id, Callback callback) { request(context, "conversation-detail", json("conversationId", id), "CONVERSATION_UNAVAILABLE", callback); }
    public static void deleteConversationAsync(Context context, String id, Callback callback) { request(context, "conversation-delete", json("conversationId", id), "CONVERSATION_DELETE_FAILED", callback); }
    public static void incidentAsync(Context context, String incidentId, Callback callback) { request(context, "incident-detail", json("incidentId", incidentId), "INCIDENT_UNAVAILABLE", callback); }

    public static void sendCommand(Context context, String command) {
        if (!controllerButtonsEnabled(context)) return;
        new Thread(() -> {
            try {
                SharedPreferences preferences = prefs(context);
                long sequence = preferences.getLong("controllerSequence", 0L) + 1L;
                post(context, "controller-command", new JSONObject().put("command", command).put("clientSequence", sequence));
                preferences.edit().putLong("controllerSequence", sequence).apply();
            } catch (Exception ignored) { }
        }, "scut-command").start();
    }

    public static void updateFcmToken(Context context, String token) {
        if (!configured(context) || token == null || token.isEmpty()) return;
        new Thread(() -> {
            try {
                post(context, "update-device", new JSONObject().put("fcmRegistrationToken", token).put("appVersion", appVersion(context)));
                prefs(context).edit().putBoolean("fcmRegistered", true).apply();
            } catch (Exception ignored) {
                prefs(context).edit().putBoolean("fcmRegistered", false).apply();
            }
        }, "scut-fcm-token").start();
    }

    public static void refreshFcmToken(Context context) {
        try {
            FirebaseMessaging.getInstance().getToken().addOnCompleteListener(task -> {
                if (task.isSuccessful()) updateFcmToken(context, task.getResult());
            });
        } catch (Exception ignored) { }
    }

    private static void request(Context context, String function, JSONObject body, String fallback, Callback callback) {
        new Thread(() -> {
            try {
                callback.complete(post(context, function, body), null);
            } catch (CloudException error) {
                callback.complete(null, error.code);
            } catch (Exception ignored) {
                callback.complete(null, fallback);
            }
        }, "scut-" + function).start();
    }

    private static JSONObject post(Context context, String function, JSONObject body) throws Exception {
        return post(CLOUD_ENDPOINT, function, body, CredentialStore.get(context));
    }

    private static JSONObject post(String endpoint, String function, JSONObject body, String credential) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint + "/functions/v1/" + function).openConnection();
        connection.setConnectTimeout(5000);
        connection.setReadTimeout(7000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type", "application/json");
        if (credential != null && !credential.isEmpty()) connection.setRequestProperty("x-scut-device-token", credential);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(body.toString().getBytes(StandardCharsets.UTF_8));
        }
        int status = connection.getResponseCode();
        String text = read(status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream());
        if (status < 200 || status >= 300) {
            String code = "REQUEST_REJECTED";
            try {
                JSONObject error = new JSONObject(text).optJSONObject("error");
                if (error != null) code = error.optString("code", code);
            } catch (Exception ignored) { }
            throw new CloudException(code);
        }
        return new JSONObject(text);
    }

    private static String read(InputStream stream) throws IOException {
        if (stream == null) return "{}";
        try (BufferedReader input = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            StringBuilder text = new StringBuilder();
            String line;
            while ((line = input.readLine()) != null) text.append(line);
            return text.toString();
        }
    }

    private static String installId(Context context) {
        SharedPreferences preferences = prefs(context);
        String id = preferences.getString("cloudInstallId", "");
        if (!id.isEmpty()) return id;
        id = UUID.randomUUID().toString();
        preferences.edit().putString("cloudInstallId", id).apply();
        return id;
    }

    private static String friendlyDeviceName() {
        String manufacturer = Build.MANUFACTURER == null ? "" : Build.MANUFACTURER.trim();
        String model = Build.MODEL == null ? "Android" : Build.MODEL.trim();
        if (!manufacturer.isEmpty() && model.toLowerCase(Locale.ROOT).startsWith(manufacturer.toLowerCase(Locale.ROOT))) return model;
        return (manufacturer + " " + model).trim();
    }

    private static String appVersion(Context context) {
        try {
            return context.getPackageManager().getPackageInfo(context.getPackageName(), 0).versionName;
        } catch (Exception ignored) {
            return "unknown";
        }
    }

    private static JSONObject json(String key, Object value) {
        JSONObject object = new JSONObject();
        try { object.put(key, value); } catch (Exception ignored) { }
        return object;
    }

    private static JSONObject page(String cursor) {
        JSONObject object = json("limit", 50);
        try { if (cursor != null && !cursor.isEmpty()) object.put("cursor", cursor); } catch (Exception ignored) { }
        return object;
    }

    private static final class CloudException extends IOException {
        final String code;
        CloudException(String code) { super(code); this.code = code; }
    }
}
