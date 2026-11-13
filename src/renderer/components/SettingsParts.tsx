import { useState } from 'react';
import { Icon } from '../icons';
import { cx } from '../lib/format';

export function KeyValueEditor({ pairs, onChange, keyPlaceholder, valuePlaceholder, addLabel }: { pairs: { key: string; value: string }[]; onChange: (pairs: { key: string; value: string }[]) => void; keyPlaceholder?: string; valuePlaceholder?: string; addLabel?: string }) {
  const [key, setKey] = useState('');
  const [value, setValue] = useState('');

  const add = () => {
    if (!key.trim()) return;
    onChange([...pairs, { key: key.trim(), value: value.trim() }]);
    setKey('');
    setValue('');
  };

  const remove = (index: number) => {
    onChange(pairs.filter((_, i) => i !== index));
  };

  return (
    <div className="key-value-editor">
      <div className="kve-row">
        <input className="kve-input" placeholder={keyPlaceholder ?? 'Key'} value={key} onChange={(e) => setKey(e.target.value)} />
        <input className="kve-input" placeholder={valuePlaceholder ?? 'Value'} value={value} onChange={(e) => setValue(e.target.value)} />
        <button type="button" className="kve-add" onClick={add}>{addLabel ?? 'Add'}</button>
      </div>
      <div className="kve-list">
        {pairs.map((p, i) => (
          <div key={i} className="kve-item">
            <span className="kve-key">{p.key}</span>
            <span className="kve-sep">=</span>
            <span className="kve-value">{p.value}</span>
            <button type="button" className="kve-remove" onClick={() => remove(i)} aria-label="Remove">
              <Icon name="x" size={13} />
            </button>
          </div>
        ))}
        {!pairs.length && <div className="kve-empty">None yet.</div>}
      </div>
    </div>
  );
}
