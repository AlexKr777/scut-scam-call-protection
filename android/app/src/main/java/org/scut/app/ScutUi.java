package org.scut.app;

import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.provider.Settings;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.animation.DecelerateInterpolator;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.text.DateFormat;
import java.util.Date;

final class ScutUi {
    static final int INK = Color.rgb(30, 33, 27);
    static final int MUTED = Color.rgb(109, 107, 98);
    static final int CANVAS = Color.rgb(244, 241, 231);
    static final int RAISED = Color.rgb(250, 248, 242);
    static final int STONE = Color.rgb(222, 215, 200);
    static final int GREEN = Color.rgb(29, 111, 73);
    static final int SOFT_GREEN = Color.rgb(191, 214, 184);
    static final int AMBER = Color.rgb(198, 144, 50);
    static final int RUST = Color.rgb(166, 76, 65);

    private ScutUi() { }

    static int dp(Context context, int value) { return Math.round(value * context.getResources().getDisplayMetrics().density); }

    static void applySystemBars(Activity activity, View root) {
        final int left = root.getPaddingLeft();
        final int top = root.getPaddingTop();
        final int right = root.getPaddingRight();
        final int bottom = root.getPaddingBottom();
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            int insetLeft;
            int insetTop;
            int insetRight;
            int insetBottom;
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars());
                insetLeft = bars.left;
                insetTop = bars.top;
                insetRight = bars.right;
                insetBottom = bars.bottom;
            } else {
                insetLeft = insets.getSystemWindowInsetLeft();
                insetTop = insets.getSystemWindowInsetTop();
                insetRight = insets.getSystemWindowInsetRight();
                insetBottom = insets.getSystemWindowInsetBottom();
            }
            view.setPadding(left + insetLeft, top + insetTop, right + insetRight, bottom + insetBottom);
            return insets;
        });
        root.requestApplyInsets();
    }

    static LinearLayout column(Context context) {
        LinearLayout layout = new LinearLayout(context);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(CANVAS);
        return layout;
    }

    static ScrollView scroll(Context context, LinearLayout content) {
        ScrollView scroll = new ScrollView(context);
        scroll.setFillViewport(true);
        scroll.setClipToPadding(false);
        scroll.addView(content, new ScrollView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return scroll;
    }

    static TextView text(Context context, CharSequence text, float size, int color, int weight) {
        TextView view = new TextView(context);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setTypeface(Typeface.create("sans-serif", weight));
        view.setLineSpacing(0, 1.12f);
        return view;
    }

    static TextView label(Context context, CharSequence text) {
        TextView view = text(context, text, 13, MUTED, Typeface.NORMAL);
        view.setLetterSpacing(0.02f);
        return view;
    }

    static TextView title(Context context, CharSequence text) { return text(context, text, 28, INK, Typeface.BOLD); }

    static Button primary(Context context, CharSequence text) {
        Button button = baseButton(context, text, Color.WHITE);
        button.setBackground(background(GREEN, dp(context, 14), 0, Color.TRANSPARENT));
        return button;
    }

    static Button secondary(Context context, CharSequence text) {
        Button button = baseButton(context, text, INK);
        button.setBackground(background(RAISED, dp(context, 14), dp(context, 1), STONE));
        return button;
    }

    static Button tertiary(Context context, CharSequence text) {
        Button button = baseButton(context, text, GREEN);
        button.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        button.setBackgroundColor(Color.TRANSPARENT);
        return button;
    }

    private static Button baseButton(Context context, CharSequence text, int color) {
        Button button = new Button(context);
        button.setText(text);
        button.setTextColor(color);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        button.setMinHeight(dp(context, 52));
        button.setPadding(dp(context, 18), 0, dp(context, 18), 0);
        button.setStateListAnimator(null);
        button.setOnTouchListener((view, event) -> {
            if (event.getAction() == MotionEvent.ACTION_DOWN) {
                view.animate().alpha(0.82f).translationY(dp(context, 1)).setDuration(90).start();
            } else if (event.getAction() == MotionEvent.ACTION_UP || event.getAction() == MotionEvent.ACTION_CANCEL) {
                view.animate().alpha(1f).translationY(0).setDuration(130).start();
            }
            return false;
        });
        return button;
    }

    static GradientDrawable background(int color, int radiusPx, int strokePx, int strokeColor) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(radiusPx);
        if (strokePx > 0) drawable.setStroke(strokePx, strokeColor);
        return drawable;
    }

    static View divider(Context context) {
        View divider = new View(context);
        divider.setBackgroundColor(STONE);
        divider.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(context, 1)));
        return divider;
    }

    static LinearLayout section(Context context) {
        LinearLayout section = column(context);
        section.setPadding(dp(context, 20), dp(context, 20), dp(context, 20), dp(context, 20));
        section.setBackground(background(RAISED, dp(context, 14), dp(context, 1), STONE));
        return section;
    }

    static LinearLayout.LayoutParams matchWrap(Context context, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(context, top);
        return params;
    }

    static LinearLayout.LayoutParams dividerParams(Context context, int top) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(context, 1));
        params.topMargin = dp(context, top);
        return params;
    }

    static void animateIn(Context context, View view, long delay) {
        if (reducedMotion(context)) return;
        view.setAlpha(0f);
        view.setTranslationY(dp(context, 7));
        view.animate().alpha(1f).translationY(0).setStartDelay(delay).setDuration(220)
                .setInterpolator(new DecelerateInterpolator()).start();
    }

    static boolean reducedMotion(Context context) {
        try { return Settings.Global.getFloat(context.getContentResolver(), Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f; }
        catch (Exception ignored) { return false; }
    }

    static String time(Context context, String iso) {
        try { return DateFormat.getTimeInstance(DateFormat.SHORT).format(Date.from(java.time.Instant.parse(iso))); }
        catch (Exception ignored) { return ""; }
    }

    static String date(Context context, String iso) {
        try { return DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date.from(java.time.Instant.parse(iso))); }
        catch (Exception ignored) { return ""; }
    }

    static String ellipsize(String value, int max) {
        if (TextUtils.isEmpty(value)) return "";
        return value.length() <= max ? value : value.substring(0, max - 1).trim() + "…";
    }
}
