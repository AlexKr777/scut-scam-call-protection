package org.scut.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Android Keystore backed storage for cloud and local pairing credentials. */
final class CredentialStore {
    private static final String CLOUD_ALIAS = "scut_cloud_device_credential";
    private static final String CLOUD_VALUE = "cloudCredentialCipher";
    private static final String CLOUD_IV = "cloudCredentialIv";
    private static final String LOCAL_ALIAS = "scut_local_pairing_credential";
    private static final String LOCAL_VALUE = "localCredentialCipher";
    private static final String LOCAL_IV = "localCredentialIv";
    private static final String PRIVATE_ALIAS = "scut_private_cache";

    private CredentialStore() { }

    static String get(Context context) {
        return get(context, CLOUD_ALIAS, CLOUD_VALUE, CLOUD_IV, "cloudCredential");
    }

    static String getLocal(Context context) {
        return get(context, LOCAL_ALIAS, LOCAL_VALUE, LOCAL_IV, "credential");
    }

    private static String get(Context context, String alias, String valueKey, String ivKey, String legacyKey) {
        SharedPreferences preferences = context.getSharedPreferences("scut", Context.MODE_PRIVATE);
        String cipherText = preferences.getString(valueKey, "");
        String iv = preferences.getString(ivKey, "");
        if (!cipherText.isEmpty() && !iv.isEmpty()) {
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, key(alias), new GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)));
                return new String(cipher.doFinal(Base64.decode(cipherText, Base64.NO_WRAP)), StandardCharsets.UTF_8);
            } catch (Exception ignored) {
                return "";
            }
        }

        // One-way migration for installations enrolled before Keystore storage.
        String legacy = preferences.getString(legacyKey, "");
        if (!legacy.isEmpty() && put(context, legacy, alias, valueKey, ivKey, legacyKey)) {
            return legacy;
        }
        return "";
    }

    static boolean put(Context context, String credential) {
        return put(context, credential, CLOUD_ALIAS, CLOUD_VALUE, CLOUD_IV, "cloudCredential");
    }

    static boolean putLocal(Context context, String credential) {
        return put(context, credential, LOCAL_ALIAS, LOCAL_VALUE, LOCAL_IV, "credential");
    }

    static void clearLocal(Context context) {
        context.getSharedPreferences("scut", Context.MODE_PRIVATE).edit()
                .remove(LOCAL_VALUE)
                .remove(LOCAL_IV)
                .remove("credential")
                .apply();
    }

    static String getPrivate(Context context, String name) {
        return get(context, PRIVATE_ALIAS, "privateCipher:" + name, "privateIv:" + name, name);
    }

    static boolean putPrivate(Context context, String name, String value) {
        return put(context, value, PRIVATE_ALIAS, "privateCipher:" + name, "privateIv:" + name, name);
    }

    static void removePrivate(Context context, String name) {
        context.getSharedPreferences("scut", Context.MODE_PRIVATE).edit()
                .remove("privateCipher:" + name)
                .remove("privateIv:" + name)
                .remove(name)
                .apply();
    }

    private static boolean put(Context context, String credential, String alias, String valueKey, String ivKey, String legacyKey) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key(alias));
            byte[] encrypted = cipher.doFinal(credential.getBytes(StandardCharsets.UTF_8));
            context.getSharedPreferences("scut", Context.MODE_PRIVATE).edit()
                    .putString(valueKey, Base64.encodeToString(encrypted, Base64.NO_WRAP))
                    .putString(ivKey, Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                    .remove(legacyKey)
                    .apply();
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    private static SecretKey key(String alias) throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        KeyStore.Entry entry = store.getEntry(alias, null);
        if (entry instanceof KeyStore.SecretKeyEntry) {
            return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build());
        return generator.generateKey();
    }
}
