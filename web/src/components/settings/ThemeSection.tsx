import { useState } from "react";
import { Brush } from "lucide-react";
import { Card, CardContent, CardHeader } from "../Card";
import { SectionHeader } from "../SectionHeader";
import {
    applyThemePreference,
    readThemePreference,
    type ThemePreference,
} from "../../theme";

const THEME_LABELS: Record<ThemePreference, string> = {
    system: "System",
    light: "Light",
    dark: "Dark",
};

export function ThemeSection() {
    const [themePreference, setThemePreference] = useState<ThemePreference>(() =>
        readThemePreference(),
    );

    return (
        <Card>
            <CardHeader>
                <SectionHeader icon={<Brush className="w-5 h-5" />} title="Theme" subtitle="Choose your appearance" />
            </CardHeader>
            <CardContent>
                <fieldset className="space-y-2">
                    <legend className="sr-only">Theme preference</legend>
                    {(["system", "light", "dark"] as const).map((option) => (
                        <label
                            key={option}
                            className="flex items-center gap-2 text-sm text-text"
                        >
                            <input
                                type="radio"
                                name="theme-preference"
                                value={option}
                                checked={themePreference === option}
                                onChange={() => {
                                    setThemePreference(option);
                                    applyThemePreference(option);
                                }}
                            />
                            {THEME_LABELS[option]}
                        </label>
                    ))}
                </fieldset>
            </CardContent>
        </Card>
    );
}
