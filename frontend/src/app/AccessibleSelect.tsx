import { useId } from 'react'

/** Native keyboard/VoiceOver semantics with the existing Astra surface tokens.
 * Astra 1.0.0's SelectField installs a document-wide Enter/Space listener and
 * reuses option IDs. Keep this fix local instead of patching the dependency.
 */
export function AccessibleSelect({label, value, onChange, options, disabled = false}: {
  label: string; value: string; onChange: (value: string) => void;
  options: {value: string; label: string}[]; disabled?: boolean;
}) {
  const id = useId()
  return <div className="sa-select"><label htmlFor={id}>{label}</label>
    <select id={id} value={value} disabled={disabled} onChange={e => onChange(e.target.value)}>
      {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select></div>
}
