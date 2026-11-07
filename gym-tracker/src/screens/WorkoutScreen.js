import { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, Vibration, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Screen from '../Screen';
import { Btn, Card, Input, Muted, T, s } from '../ui';
import { lastSetsFor, useStore } from '../store';
import { C, uid } from '../theme';

const mmss = (sec) => `${Math.floor(sec / 60)}:${String(Math.max(0, sec % 60)).padStart(2, '0')}`;

export default function WorkoutScreen() {
  const { state, update } = useStore();
  const w = state.active;
  const [now, setNow] = useState(Date.now());
  const [restEnd, setRestEnd] = useState(null);
  const [newEx, setNewEx] = useState('');

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const restLeft = restEnd ? Math.ceil((restEnd - now) / 1000) : null;
  useEffect(() => {
    if (restEnd && restLeft <= 0) {
      Vibration.vibrate([0, 400, 200, 400]);
      setRestEnd(null);
    }
  }, [restLeft, restEnd]);

  const setW = (fn) => update((st) => ({ active: fn(st.active) }));
  const setEx = (exId, fn) =>
    setW((a) => ({ ...a, exercises: a.exercises.map((e) => (e.id === exId ? fn(e) : e)) }));
  const setSet = (exId, i, patch) =>
    setEx(exId, (e) => ({ ...e, sets: e.sets.map((x, j) => (j === i ? { ...x, ...patch } : x)) }));

  const toggleDone = (ex, i, prev) => {
    const set = ex.sets[i];
    if (!set.done) {
      // Fill empty fields from the placeholder (last session) when ticking.
      const kg = set.kg !== '' ? set.kg : prev?.kg ?? '';
      const reps = set.reps !== '' ? set.reps : prev?.reps ?? String(ex.target ?? '').split('-').pop();
      setSet(ex.id, i, { done: true, kg: String(kg), reps: String(reps) });
      if (ex.rest) setRestEnd(Date.now() + ex.rest * 1000);
    } else {
      setSet(ex.id, i, { done: false });
    }
  };

  const finish = () => {
    const exercises = w.exercises
      .map((e) => ({ ...e, sets: e.sets.filter((x) => x.done) }))
      .filter((e) => e.sets.length);
    if (!exercises.length) {
      Alert.alert('Nessuna serie completata', 'Spunta almeno una serie oppure annulla l\'allenamento.');
      return;
    }
    Alert.alert('Termina allenamento?', '', [
      { text: 'Continua', style: 'cancel' },
      {
        text: 'Salva',
        onPress: () =>
          update((st) => ({
            active: null,
            history: [{ ...st.active, exercises, finishedAt: new Date().toISOString() }, ...st.history],
          })),
      },
    ]);
  };

  const discard = () =>
    Alert.alert('Annullare l\'allenamento?', 'I dati di questa sessione andranno persi.', [
      { text: 'No', style: 'cancel' },
      { text: 'Annulla allenamento', style: 'destructive', onPress: () => update(() => ({ active: null })) },
    ]);

  const addExercise = () => {
    if (!newEx.trim()) return;
    const last = lastSetsFor(state.history, newEx.trim());
    setW((a) => ({
      ...a,
      exercises: [
        ...a.exercises,
        {
          id: uid(),
          name: newEx.trim(),
          target: '',
          rest: 90,
          sets: Array.from({ length: 3 }, (_, i) => ({ kg: last?.[i]?.kg ?? '', reps: '', done: false })),
        },
      ],
    }));
    setNewEx('');
  };

  const elapsed = Math.floor((now - new Date(w.startedAt).getTime()) / 1000);
  const doneSets = w.exercises.reduce((t, e) => t + e.sets.filter((x) => x.done).length, 0);
  const totSets = w.exercises.reduce((t, e) => t + e.sets.length, 0);

  return (
    <View style={{ flex: 1, backgroundColor: C.bg }}>
      <Screen
        footer={
          restEnd ? (
            <SafeAreaView edges={['bottom']} style={st.rest}>
              <Pressable onPress={() => setRestEnd((r) => r - 15000)} style={st.restBtn}>
                <Text style={st.restBtnText}>−15</Text>
              </Pressable>
              <View style={{ alignItems: 'center', flex: 1 }}>
                <Text style={{ color: C.accentText, fontWeight: '700', fontSize: 12 }}>RECUPERO</Text>
                <Text style={{ color: C.accentText, fontWeight: '900', fontSize: 30 }}>{mmss(restLeft)}</Text>
              </View>
              <Pressable onPress={() => setRestEnd((r) => r + 15000)} style={st.restBtn}>
                <Text style={st.restBtnText}>+15</Text>
              </Pressable>
              <Pressable onPress={() => setRestEnd(null)} style={st.restBtn}>
                <Text style={st.restBtnText}>Salta</Text>
              </Pressable>
            </SafeAreaView>
          ) : null
        }
      >
        <View style={[s.row, { justifyContent: 'space-between', marginBottom: 4 }]}>
          <Muted>⏱ {mmss(elapsed)} · {doneSets}/{totSets} serie</Muted>
          <Btn small label="Termina" onPress={finish} />
        </View>
        <Input
          value={w.name}
          onChangeText={(name) => setW((a) => ({ ...a, name }))}
          style={{ fontSize: 22, fontWeight: '800', backgroundColor: 'transparent', paddingHorizontal: 0 }}
        />

        {w.exercises.map((ex) => {
          const prev = lastSetsFor(state.history, ex.name);
          return (
            <Card key={ex.id}>
              <View style={[s.row, { justifyContent: 'space-between', marginBottom: 8 }]}>
                <View style={{ flex: 1 }}>
                  <T style={{ fontWeight: '800', fontSize: 17 }}>{ex.name}</T>
                  <Muted>
                    {ex.target ? `Target ${ex.target} rip · ` : ''}rec. {ex.rest}s
                  </Muted>
                </View>
                <Pressable
                  hitSlop={10}
                  onPress={() =>
                    Alert.alert('Rimuovere esercizio?', ex.name, [
                      { text: 'No', style: 'cancel' },
                      {
                        text: 'Rimuovi',
                        style: 'destructive',
                        onPress: () => setW((a) => ({ ...a, exercises: a.exercises.filter((e) => e.id !== ex.id) })),
                      },
                    ])
                  }
                >
                  <Text style={{ color: C.muted, fontSize: 20 }}>✕</Text>
                </Pressable>
              </View>

              <View style={[s.row, st.head]}>
                <Text style={[st.hc, { width: 28 }]}>#</Text>
                <Text style={[st.hc, { flex: 1 }]}>Prima</Text>
                <Text style={[st.hc, { width: 72 }]}>kg</Text>
                <Text style={[st.hc, { width: 60 }]}>rip</Text>
                <View style={{ width: 44 }} />
              </View>

              {ex.sets.map((set, i) => {
                const p = prev?.[i];
                return (
                  <View key={i} style={[s.row, st.setRow, set.done && { backgroundColor: '#1F2A12' }]}>
                    <Text style={[st.cell, { width: 28, color: C.muted }]}>{i + 1}</Text>
                    <Text style={[st.cell, { flex: 1, color: C.muted, fontSize: 13 }]}>
                      {p ? `${p.kg}×${p.reps}` : '—'}
                    </Text>
                    <Input
                      value={String(set.kg)}
                      onChangeText={(kg) => setSet(ex.id, i, { kg: kg.replace(',', '.') })}
                      keyboardType="decimal-pad"
                      placeholder={p ? String(p.kg) : '0'}
                      style={st.num}
                      selectTextOnFocus
                    />
                    <Input
                      value={String(set.reps)}
                      onChangeText={(reps) => setSet(ex.id, i, { reps })}
                      keyboardType="number-pad"
                      placeholder={p ? String(p.reps) : String(ex.target || '0').split('-').pop()}
                      style={[st.num, { width: 52 }]}
                      selectTextOnFocus
                    />
                    <Pressable
                      onPress={() => toggleDone(ex, i, p)}
                      style={[st.check, set.done && { backgroundColor: C.ok, borderColor: C.ok }]}
                    >
                      <Text style={{ color: set.done ? C.bg : C.muted, fontWeight: '900' }}>✓</Text>
                    </Pressable>
                  </View>
                );
              })}

              <View style={[s.row, { gap: 8, marginTop: 8 }]}>
                <Btn
                  small
                  kind="ghost"
                  label="+ Serie"
                  style={{ flex: 1 }}
                  onPress={() =>
                    setEx(ex.id, (e) => {
                      const l = e.sets[e.sets.length - 1];
                      return { ...e, sets: [...e.sets, { kg: l?.kg ?? '', reps: '', done: false }] };
                    })
                  }
                />
                {ex.sets.length > 1 && (
                  <Btn
                    small
                    kind="ghost"
                    label="− Serie"
                    style={{ flex: 1 }}
                    onPress={() => setEx(ex.id, (e) => ({ ...e, sets: e.sets.slice(0, -1) }))}
                  />
                )}
              </View>
            </Card>
          );
        })}

        <Card>
          <Muted style={{ marginBottom: 8 }}>Aggiungi esercizio</Muted>
          <View style={[s.row, { gap: 8 }]}>
            <Input
              value={newEx}
              onChangeText={setNewEx}
              placeholder="Es. Dip alle parallele"
              style={{ flex: 1 }}
              onSubmitEditing={addExercise}
              returnKeyType="done"
            />
            <Btn small label="Aggiungi" onPress={addExercise} />
          </View>
        </Card>

        <Btn kind="danger" label="Annulla allenamento" onPress={discard} style={{ marginTop: 8 }} />
      </Screen>
    </View>
  );
}

const st = StyleSheet.create({
  head: { paddingHorizontal: 4, marginBottom: 4 },
  hc: { color: C.muted, fontSize: 12, fontWeight: '700' },
  setRow: { paddingVertical: 4, paddingHorizontal: 4, borderRadius: 8, gap: 6 },
  cell: { color: C.text, fontSize: 15 },
  num: { width: 66, textAlign: 'center', paddingVertical: 8, paddingHorizontal: 4 },
  check: {
    width: 38,
    height: 38,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: C.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rest: { backgroundColor: C.accent, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingTop: 10, gap: 6 },
  restBtn: { paddingVertical: 10, paddingHorizontal: 12, backgroundColor: 'rgba(0,0,0,0.12)', borderRadius: 10, marginBottom: 10 },
  restBtnText: { color: C.accentText, fontWeight: '800' },
});
