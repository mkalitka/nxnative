// Widen a game's camera into its existing 16:9 canvas, then restore its shape at present.
// UI bounds are transformed about the canvas centre, including the scissor.
#pragma once
#include <math.h>

static inline float nvn_widescreen_ratio(double w, double h) {
    double a = h > 0 ? w / h : 0;
    return isfinite(a) && a > (16.0 / 9.0) * 1.01 && a <= 8 ? (float)a : 0;
}
static inline double nvn_widescreen_x(double x, double width, double factor) {
    return width * 0.5 + (x - width * 0.5) / factor;
}
