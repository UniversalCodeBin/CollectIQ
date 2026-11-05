import { useId } from "react";
import styles from "./ImportPage.module.css";

export type Choice = { value: string; label: string; hint?: string };

type Props = {
  label: string;
  choices: Choice[];
  value: string | undefined;
  onChange: (value: string) => void;
};

/** One question with a radio per answer. The group is named, so a screen reader announces the question. */
export function ChoiceGroup({ label, choices, value, onChange }: Props) {
  const id = useId();
  return (
    <div role="radiogroup" aria-labelledby={`${id}-label`} className={styles.choices}>
      <span id={`${id}-label`} className={styles.question}>
        {label}
      </span>
      {choices.map((choice) => (
        <label key={choice.value} className={styles.choice}>
          <input type="radio" name={id} checked={value === choice.value} onChange={() => onChange(choice.value)} />
          <span>{choice.label}</span>
          {choice.hint && <span className={styles.hint}>{choice.hint}</span>}
        </label>
      ))}
    </div>
  );
}
