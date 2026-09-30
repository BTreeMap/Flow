/** PWA environment detection shared across install/notification flows. */

export function isIOS(): boolean {
    // `navigator.platform` is the only reliable iPadOS-on-desktop-UA signal;
    // read it through a non-deprecated typed view to keep the check.
    const platform = (navigator as { platform: string }).platform;
    return (
        /iPad|iPhone|iPod/.test(navigator.userAgent) ||
        (platform === "MacIntel" && navigator.maxTouchPoints > 1)
    );
}

export function isStandalone(): boolean {
    return (
        window.matchMedia("(display-mode: standalone)").matches ||
        (navigator as { standalone?: boolean }).standalone === true
    );
}
