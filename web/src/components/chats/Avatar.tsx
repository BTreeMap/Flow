export function Avatar({ name }: { name: string }) {
    const initials = (name || "?")
        .split(/\s+/)
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
    return (
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary/20 to-accent/15 text-primary flex items-center justify-center text-[15px] font-semibold shrink-0 ring-1 ring-inset ring-primary/10">
            {initials}
        </div>
    );
}
