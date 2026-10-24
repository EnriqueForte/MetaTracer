/**
 * Origin-root prefix for app-relative URLs (T11).
 *
 * Web V2 serves from `/` now, so the constant is empty. It is kept (rather
 * than deleted) so the one caller keeps composing paths idiomatically instead
 * of hardcoding absolute ones.
 */
export const BASE_PATH = "";

/** Mirrors `metatracer.__version__`. Health does not return a version. */
export const APP_VERSION = "0.6.0";
