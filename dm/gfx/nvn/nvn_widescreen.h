// Fit a game's camera to a screen wider than 16:9 inside its existing 16:9 canvas, then restore its shape at present.
// UI bounds are narrowed about the canvas centre, including the scissor, so the HUD keeps its 16:9 proportions.
// A taller screen is not this path: the game renders that shape (DM_SCREEN_ASPECT, loader.c's screen-shape stubs).
#pragma once
#include <math.h>

// The camera aspect for a w x h screen: its ratio when it is wider than 16:9 by over 1 % (up to 8), else 0 (the original; front.h front_aspect_wider).
static inline float nvn_widescreen_ratio(double w, double h) {
    double a = h > 0 ? w / h : 0;
    return isfinite(a) && a > 16.0 / 9.0 * 1.01 && a <= 8 ? (float)a : 0;
}
// Squeeze a coordinate x of a span width about its centre by factor (> 1 narrows).
static inline double nvn_widescreen_x(double x, double width, double factor) {
    return width * 0.5 + (x - width * 0.5) / factor;
}
