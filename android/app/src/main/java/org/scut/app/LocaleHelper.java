package org.scut.app;

import android.content.Context;
import android.content.res.Configuration;
import android.content.res.Resources;
import android.os.Build;

import java.util.Locale;

final class LocaleHelper {
    private LocaleHelper() { }

    static Context apply(Context context) {
        String language = context.getSharedPreferences("scut", Context.MODE_PRIVATE).getString("language", "system");
        Locale locale;
        if (language == null || "system".equals(language)) {
            Configuration system = Resources.getSystem().getConfiguration();
            locale = Build.VERSION.SDK_INT >= 24 ? system.getLocales().get(0) : system.locale;
        } else {
            locale = Locale.forLanguageTag(language);
        }
        Locale.setDefault(locale);
        Configuration configuration = new Configuration(context.getResources().getConfiguration());
        configuration.setLocale(locale);
        if (Build.VERSION.SDK_INT >= 24) configuration.setLocales(new android.os.LocaleList(locale));
        return context.createConfigurationContext(configuration);
    }

    static void save(Context context, String language) {
        context.getSharedPreferences("scut", Context.MODE_PRIVATE).edit().putString("language", language).apply();
    }
}
