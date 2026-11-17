// The named viewports every renderer here uses (shots, audit, motion), so a name means one size everywhere.
// Touch sizes get isMobile and hasTouch: a resized desktop window is not a phone (coding-mistakes, 2026-07-17).
export const VIEWPORTS = {
  'mac-1512x820': { width: 1512, height: 820, isMobile: false, hasTouch: false },
  'mac-1440x780': { width: 1440, height: 780, isMobile: false, hasTouch: false },
  'desktop-1440x900': { width: 1440, height: 900, isMobile: false, hasTouch: false },
  // a big screen: more columns or larger type, never a narrow strip in blank space
  'monitor-1920x1080': { width: 1920, height: 1080, isMobile: false, hasTouch: false },
  'monitor-2560x1440': { width: 2560, height: 1440, isMobile: false, hasTouch: false },
  'tablet-820x1180': { width: 820, height: 1180, isMobile: true, hasTouch: true },
  'phone-390x844': { width: 390, height: 844, isMobile: true, hasTouch: true },
  'phone-landscape-844x390': { width: 844, height: 390, isMobile: true, hasTouch: true },
  'small-320x568': { width: 320, height: 568, isMobile: true, hasTouch: true },
  // the original names, kept working
  desktop: { width: 1440, height: 900, isMobile: false, hasTouch: false },
  laptop: { width: 1280, height: 720, isMobile: false, hasTouch: false },
  tablet: { width: 820, height: 1180, isMobile: true, hasTouch: true },
  phone: { width: 390, height: 844, isMobile: true, hasTouch: true },
  small: { width: 320, height: 568, isMobile: true, hasTouch: true },
};
