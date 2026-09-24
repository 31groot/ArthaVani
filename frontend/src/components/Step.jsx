import { Check } from "lucide-react";

function Step({ index, label, active, done }) {
  return (
    <div className={`step ${active ? "active" : ""} ${done ? "done" : ""}`}>
      <span>{done ? <Check size={13} /> : index}</span>
      <strong>{label}</strong>
    </div>
  );
}

export default Step;
