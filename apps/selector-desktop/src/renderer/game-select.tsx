import React, { useId, useState } from 'react';

export function GameSelect({
  value,
  games,
  disabled,
  onChange,
  onAdd,
}: {
  value: string;
  games: string[];
  disabled: boolean;
  onChange: (value: string) => void;
  onAdd: (value: string) => Promise<void>;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [showAll, setShowAll] = useState(false);
  const filtered = games.filter(
    (game) =>
      showAll || game.toLowerCase().includes(value.trim().toLowerCase()),
  );
  const canAdd =
    Boolean(value.trim()) &&
    !games.some((game) => game.toLowerCase() === value.trim().toLowerCase());
  const options = [...filtered, ...(canAdd ? [value.trim()] : [])];
  function choose(index: number) {
    const selected = options[index];
    if (!selected) return;
    if (index === filtered.length && canAdd) void onAdd(selected);
    else onChange(selected);
    setOpen(false);
    setActive(-1);
  }
  return (
    <div
      className="game-select"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <label htmlFor={`${id}-input`}>Nazwa gry</label>
      <div className="game-input">
        <input
          id={`${id}-input`}
          autoFocus
          role="combobox"
          aria-label="Nazwa gry"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          aria-activedescendant={
            open && active >= 0 && options[active]
              ? `${id}-${active}`
              : undefined
          }
          required
          maxLength={80}
          autoComplete="off"
          disabled={disabled}
          value={value}
          placeholder="Wybierz lub wpisz grę"
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            onChange(event.target.value);
            setShowAll(false);
            setOpen(true);
            setActive(-1);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              event.stopPropagation();
              if (open && active >= 0) choose(active);
              else if (value.trim()) {
                void onAdd(value);
                setOpen(false);
              }
            } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
              event.preventDefault();
              setOpen(true);
              setActive(
                Math.max(
                  0,
                  Math.min(
                    options.length - 1,
                    active + (event.key === 'ArrowDown' ? 1 : -1),
                  ),
                ),
              );
            } else if (event.key === 'Escape') {
              event.preventDefault();
              setOpen(false);
            }
          }}
        />
        <button
          type="button"
          className="secondaryButton"
          aria-label="Pokaż gry"
          disabled={disabled}
          aria-expanded={open}
          onClick={() => {
            setShowAll(true);
            setOpen(!open);
            setActive(-1);
          }}
        >
          ▾
        </button>
      </div>
      {open && (
        <ul
          id={`${id}-list`}
          role="listbox"
          aria-label="Gry"
          className="game-options"
        >
          {options.map((game, index) => (
            <li
              key={game}
              id={`${id}-${index}`}
              role="option"
              aria-selected={active === index}
              className={active === index ? 'active' : ''}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                if (!disabled) choose(index);
              }}
            >
              {index === filtered.length && canAdd
                ? `Dodaj „${game}” (Enter)`
                : game}
            </li>
          ))}
          {options.length === 0 && (
            <li className="game-empty">Wpisz nazwę i naciśnij Enter</li>
          )}
        </ul>
      )}
    </div>
  );
}
