import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { SelectorBridge, SourceIndex } from '../contracts.ts';
import './style.css';
declare global {
  interface Window {
    selector: SelectorBridge;
  }
}
function App() {
  const [source, setSource] = useState<SourceIndex | null>(null);
  const [position, setPosition] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function pick() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await window.selector.pickSource();
      if (!result.ok) setError(result.error.message);
      else if (result.value) {
        setSource(result.value);
        setPosition(0);
      }
    } catch {
      setError('Brak odpowiedzi aplikacji. Spróbuj ponownie.');
    } finally {
      setBusy(false);
    }
  }
  const image = source?.images[position];
  return (
    <main>
      <header>
        <h1>Selektor zdjęć</h1>
        <p>Zdjęcia pozostają na tym komputerze.</p>
      </header>
      <nav>
        <button disabled={busy} onClick={() => void pick()}>
          {busy ? 'Wczytywanie…' : 'Wybierz katalog zdjęć'}
        </button>
        <button
          onClick={() =>
            void window.selector.openLogs().then((r) => {
              if (!r.ok) setError(r.error.message);
            })
          }
        >
          Otwórz logi
        </button>
      </nav>
      {error && <p role="alert">{error}</p>}
      {source && (
        <p>
          {source.name} · {source.images.length} zdjęć JPEG
        </p>
      )}
      {image ? (
        <>
          <nav>
            <button
              disabled={!position}
              onClick={() => setPosition(position - 1)}
            >
              Poprzednie
            </button>
            <span>
              {position + 1} / {source!.images.length} · {image.relativePath}
            </span>
            <button
              disabled={position === source!.images.length - 1}
              onClick={() => setPosition(position + 1)}
            >
              Następne
            </button>
          </nav>
          <section className="preview">
            <img
              key={image.id}
              src={image.url}
              alt={image.name}
              onError={() =>
                setError(
                  'Nie można odczytać zdjęcia. Plik jest niedostępny, uszkodzony lub zmieniony.',
                )
              }
            />
          </section>
        </>
      ) : (
        <p>
          {source
            ? 'Katalog nie zawiera zdjęć JPEG.'
            : 'Wybierz lokalny katalog, aby wyświetlić zdjęcia.'}
        </p>
      )}
    </main>
  );
}
createRoot(document.getElementById('root')!).render(<App />);
