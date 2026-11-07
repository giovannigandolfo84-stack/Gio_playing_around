export const C = {
  bg: '#0E0F12',
  card: '#181A20',
  card2: '#22252D',
  border: '#2C3039',
  text: '#F2F3F5',
  muted: '#8B909B',
  accent: '#C6F432',
  accentText: '#0E0F12',
  danger: '#FF5A5F',
  ok: '#3DDC97',
};

export const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

export const fmtDate = (iso) =>
  new Date(iso).toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' });

export const fmtDuration = (ms) => {
  const m = Math.round(ms / 60000);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m} min`;
};

// Epley estimated 1RM
export const e1rm = (kg, reps) => (reps > 0 ? kg * (1 + reps / 30) : 0);

export const sessionVolume = (s) =>
  s.exercises.reduce(
    (t, ex) => t + ex.sets.filter((x) => x.done).reduce((a, x) => a + (+x.kg || 0) * (+x.reps || 0), 0),
    0
  );
