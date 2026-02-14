import type { ReactNode } from "react";
import { AlertCircle, CheckCircle, Info, XCircle } from "lucide-react";

interface AlertProps {
  variant?: "info" | "success" | "warning" | "error";
  children: ReactNode;
  className?: string;
  "data-testid"?: string;
}

const icons = {
  info: Info,
  success: CheckCircle,
  warning: AlertCircle,
  error: XCircle,
};

const styles = {
  info: "bg-primary/10 text-primary border-primary/20",
  success: "bg-success/10 text-success border-success/20",
  warning: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
  error: "bg-danger/10 text-danger border-danger/20",
};

export function Alert({ variant = "info", children, className = "", "data-testid": testId }: AlertProps) {
  const Icon = icons[variant];
  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-2xl border ${styles[variant]} ${className}`}
      role="alert"
      data-testid={testId}
    >
      <Icon className="w-5 h-5 shrink-0 mt-0.5" />
      <div className="text-sm">{children}</div>
    </div>
  );
}
