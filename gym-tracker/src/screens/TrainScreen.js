import { View } from 'react-native';
import Screen from '../Screen';
import { Btn, Card, Muted, T, Title, s } from '../ui';
import { lastSetsFor, useStore } from '../store';
import { C, fmtDate, uid } from '../theme';

export function startWorkout(update, day) {
  update((st) => ({
    active: {
      id: uid(),
      dayId: day?.id ?? null,
      name: day?.name ?? 'Allenamento libero',
      startedAt: new Date().toISOString(),
      exercises: (day?.exercises ?? []).map((ex) => {
        const last = lastSetsFor(st.history, ex.name);
        return {
          id: uid(),
          name: ex.name,
          target: ex.reps,
          rest: ex.rest,
          sets: Array.from({ length: ex.sets }, (_, i) => ({
            kg: last?.[i]?.kg ?? last?.[last.length - 1]?.kg ?? '',
            reps: '',
            done: false,
          })),
        };
      }),
    },
  }));
}

export default function TrainScreen() {
  const { state, update } = useStore();
  const { program, history } = state;

  const lastDayId = history[0]?.dayId;
  const lastIdx = program.findIndex((d) => d.id === lastDayId);
  const next = program.length ? program[(lastIdx + 1) % program.length] : null;

  const weekAgo = Date.now() - 7 * 86400000;
  const thisWeek = history.filter((h) => new Date(h.startedAt).getTime() > weekAgo).length;

  return (
    <Screen>
      <Title sub={new Date().toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' })}>
        Allena
      </Title>

      <View style={[s.row, { gap: 12, marginBottom: 12 }]}>
        <Card style={{ flex: 1, marginBottom: 0 }}>
          <Muted>Ultimi 7 giorni</Muted>
          <T style={{ fontSize: 28, fontWeight: '800' }}>{thisWeek}</T>
        </Card>
        <Card style={{ flex: 1, marginBottom: 0 }}>
          <Muted>Totale sessioni</Muted>
          <T style={{ fontSize: 28, fontWeight: '800' }}>{history.length}</T>
        </Card>
      </View>

      {next && (
        <Card style={{ borderColor: C.accent, borderWidth: 1 }}>
          <Muted style={{ color: C.accent, fontWeight: '700' }}>PROSSIMO</Muted>
          <T style={{ fontSize: 20, fontWeight: '800', marginVertical: 6 }}>{next.name}</T>
          <Muted style={{ marginBottom: 12 }}>
            {next.exercises.map((e) => e.name).join(' · ')}
          </Muted>
          {history[0] && <Muted style={{ marginBottom: 12 }}>Ultimo: {history[0].name} – {fmtDate(history[0].startedAt)}</Muted>}
          <Btn label="Inizia allenamento" onPress={() => startWorkout(update, next)} />
        </Card>
      )}

      <Muted style={{ marginTop: 8, marginBottom: 8, fontWeight: '700' }}>ALTRE SCHEDE</Muted>
      {program
        .filter((d) => d !== next)
        .map((d) => (
          <Card key={d.id} style={[s.row, { justifyContent: 'space-between' }]}>
            <View style={{ flex: 1, paddingRight: 10 }}>
              <T style={{ fontWeight: '700' }}>{d.name}</T>
              <Muted>{d.exercises.length} esercizi</Muted>
            </View>
            <Btn small kind="ghost" label="Inizia" onPress={() => startWorkout(update, d)} />
          </Card>
        ))}
      <Btn kind="ghost" label="+ Allenamento libero" onPress={() => startWorkout(update, null)} style={{ marginTop: 4 }} />
    </Screen>
  );
}
