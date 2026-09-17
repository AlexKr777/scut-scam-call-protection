package org.scut.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.Context;
import android.net.Uri;
import android.os.Build;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import org.json.JSONObject;

public class ScutFirebaseService extends FirebaseMessagingService {
    private static final String CHANNEL = "scut_incidents";

    @Override protected void attachBaseContext(Context base) { super.attachBaseContext(LocaleHelper.apply(base)); }

    @Override public void onNewToken(String token) { CloudControl.updateFcmToken(this, token); }

    @Override public void onMessageReceived(RemoteMessage message) {
        if ("NEUTRAL_TEST".equals(message.getData().get("kind"))) {
            showConnectivityTest();
            return;
        }
        String incidentId = message.getData().get("incidentId");
        if (incidentId == null || incidentId.isEmpty()) return;
        createChannel();
        show(incidentId, getString(R.string.alert_attention), getString(R.string.alert_open_context));
        CloudControl.incidentAsync(this, incidentId, (result, error) -> {
            JSONObject incident = result == null ? null : result.optJSONObject("incident");
            if (incident == null) return;
            String state = incident.optString("state");
            boolean cleared = "CLEARED".equals(state) || "USER_DISMISSED".equals(state);
            String title = cleared ? getString(R.string.alert_cleared)
                    : ("AUTO".equals(incident.optString("source")) || "MERGED".equals(incident.optString("source")))
                    ? getString(R.string.alert_possible_scam) : getString(R.string.alert_attention);
            show(incidentId, title, cleared ? getString(R.string.alert_cleared) : getString(R.string.alert_open_context));
        });
    }

    private void showConnectivityTest() {
        String channelId = "scut_connectivity";
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(channelId, "SCUT — связь", NotificationManager.IMPORTANCE_DEFAULT));
        Intent intent = new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent content = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String body = "Активного звонка сейчас нет. Связь между устройствами работает.";
        Notification notification = new Notification.Builder(this, channelId)
                .setSmallIcon(R.drawable.ic_scut_notification)
                .setContentTitle("SCUT подключён")
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(content)
                .setCategory(Notification.CATEGORY_STATUS)
                .setAutoCancel(true)
                .build();
        manager.notify("scut_connectivity", 0, notification);
    }

    private void show(String incidentId, String title, String body) {
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("scut://incident/" + incidentId), this, MainActivity.class)
                .putExtra("incidentId", incidentId)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent content = PendingIntent.getActivity(this, incidentId.hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_scut_notification)
                .setColor(ScutUi.GREEN)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(content)
                .setCategory(Notification.CATEGORY_ALARM)
                .setAutoCancel(true)
                .build();
        getSystemService(NotificationManager.class).notify(incidentId.hashCode(), notification);
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, getString(R.string.notification_channel_incidents), NotificationManager.IMPORTANCE_HIGH);
            channel.enableVibration(true);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
    }
}
