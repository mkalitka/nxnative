// Fit a game's camera to the screen's shape inside its existing 16:9 canvas, then restore its shape at present.
// UI bounds are transformed about the canvas centre, including the scissor: narrowed on a screen wider
// than 16:9, flattened on a narrower one, so the HUD keeps its 16:9 proportions either way.
#pragma once
#include <math.h>

// The camera aspect for a w x h screen: its ratio when that differs from 16:9 by over 1 % (0.5 to 8), else 0 (the original).
static inline float nvn_widescreen_ratio(double w, double h) {
    double a = h > 0 ? w / h : 0;
    return isfinite(a) && a >= 0.5 && a <= 8 && fabs(a / (16.0 / 9.0) - 1) > 0.01 ? (float)a : 0;
}
// Squeeze a coordinate x of a span width about its centre by factor (> 1 narrows).
static inline double nvn_widescreen_x(double x, double width, double factor) {
    return width * 0.5 + (x - width * 0.5) / factor;
}
