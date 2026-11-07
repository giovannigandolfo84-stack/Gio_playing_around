import { createContext, useContext, useEffect, useRef, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEFAULT_PROGRAM } from './defaultProgram';

const KEY = 'gymtracker:v1';
const Ctx = createContext(null);

const initial = { program: DEFAULT_PROGRAM, history: [], active: null };

export function StoreProvider({ children }) {
  const [state, setState] = useState(initial);
  const [ready, setReady] = useState(false);
  const loaded = useRef(false);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (raw) setState({ ...initial, ...JSON.parse(raw) });
      })
      .catch(() => {})
      .finally(() => {
        loaded.current = true;
        setReady(true);
      });
  }, []);

  useEffect(() => {
    if (loaded.current) AsyncStorage.setItem(KEY, JSON.stringify(state)).catch(() => {});
  }, [state]);

  const update = (fn) => setState((s) => ({ ...s, ...fn(s) }));

  return <Ctx.Provider value={{ state, update, ready }}>{children}</Ctx.Provider>;
}

export const useStore = () => useContext(Ctx);

// Last logged sets for an exercise name (most recent finished session that has it)
export function lastSetsFor(history, name) {
  for (const s of history) {
    const ex = s.exercises.find((e) => e.name === name);
    if (ex && ex.sets.some((x) => x.done)) return ex.sets.filter((x) => x.done);
  }
  return null;
}
