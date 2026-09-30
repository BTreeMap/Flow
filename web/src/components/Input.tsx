import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({
  label,
  error,
  className = "",
  id,
  ...props
}: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
  return (
    <div className="space-y-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-sm font-medium text-text"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full px-3.5 py-2.5 bg-surface-2 border border-border rounded-md text-[16px] text-text placeholder:text-text-subtle outline-none transition-[border-color,box-shadow,background-color] duration-200 ease-[var(--ease-out)] hover:border-text-subtle/40 focus:bg-surface focus:border-primary focus:ring-2 focus:ring-focus ${error ? "border-danger focus:border-danger focus:ring-danger/30" : ""
          } ${className}`}
        {...props}
      />
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
