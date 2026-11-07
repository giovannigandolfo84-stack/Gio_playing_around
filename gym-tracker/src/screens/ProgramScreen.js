import { useState } from 'react';
import { Alert, Pressable, Share, Text, View } from 'react-native';
import Screen from '../Screen';
import { Btn, Card, Input, Muted, T, Title, s } from '../ui';
import { useStore } from '../store';
import { DEFAULT_PROGRAM } from '../defaultProgram';
import { C, uid } from '../theme';

function DayEditor({ day, onChange, onDelete, onClose }) {
  const setEx = (id, patch) =>
    onChange({ ...day, exercises: day.exercises.map((e) => (e.id === id ? { ...e, ...patch } : e)) });
  const move = (i, d) => {
    const ex = [...day.exercises];
    const j = i + d;
    if (j < 0 || j >= ex.length) return;
    [ex[i], ex[j]] = [ex[j], ex[i]];
    onChange({ ...day, exercises: ex });
  };

  return (
    <Card style={{ borderColor: C.accent, borderWidth: 1 }}>
      <Muted style={{ marginBottom: 6 }}>Nome scheda</Muted>
      <Input value={day.name} onChangeText={(name) => onChange({ ...day, name })} style={{ fontWeight: '700' }} />

      {day.exercises.map((ex, i) => (
        <View key={ex.id} style={{ marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: C.border }}>
          <View style={[s.row, { gap: 8 }]}>
            <Input
              value={ex.name}
              onChangeText={(name) => setEx(ex.id, { name })}
              placeholder="Esercizio"
              style={{ flex: 1 }}
            />
            <Pressable hitSlop={8} onPress={() => move(i, -1)}>
              <Text style={{ color: C.muted, fontSize: 18 }}>↑</Text>
            </Pressable>
            <Pressable hitSlop={8} onPress={() => move(i, 1)}>
              <Text style={{ color: C.muted, fontSize: 18 }}>↓</Text>
            </Pressable>
            <Pressable
              hitSlop={8}
              onPress={() => onChange({ ...day, exercises: day.exercises.filter((e) => e.id !== ex.id) })}
            >
              <Text style={{ color: C.danger, fontSize: 18 }}>✕</Text>
            </Pressable>
          </View>
          <View style={[s.row, { gap: 8, marginTop: 8 }]}>
            {[
              ['Serie', 'sets', 'number-pad'],
              ['Rip', 'reps', 'numbers-and-punctuation'],
              ['Rec (s)', 'rest', 'number-pad'],
            ].map(([label, key, kb]) => (
              <View key={key} style={{ flex: 1 }}>
                <Muted style={{ fontSize: 12, marginBottom: 4 }}>{label}</Muted>
                <Input
                  value={String(ex[key])}
                  keyboardType={kb}
                  onChangeText={(v) => setEx(ex.id, { [key]: key === 'reps' ? v : parseInt(v, 10) || 0 })}
                  style={{ textAlign: 'center' }}
                />
              </View>
            ))}
          </View>
        </View>
      ))}

      <Btn
        small
        kind="ghost"
        label="+ Esercizio"
        style={{ marginTop: 14 }}
        onPress={() =>
          onChange({ ...day, exercises: [...day.exercises, { id: uid(), name: '', sets: 3, reps: '10', rest: 90 }] })
        }
      />
      <View style={[s.row, { gap: 8, marginTop: 10 }]}>
        <Btn small kind="danger" label="Elimina scheda" style={{ flex: 1 }} onPress={onDelete} />
        <Btn small label="Fatto" style={{ flex: 1 }} onPress={onClose} />
      </View>
    </Card>
  );
}

export default function ProgramScreen() {
  const { state, update } = useStore();
  const [editing, setEditing] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importText, setImportText] = useState('');

  const setProgram = (program) => update(() => ({ program }));

  const doImport = () => {
    try {
      const data = JSON.parse(importText);
      const program = Array.isArray(data) ? data : data.program;
      if (!Array.isArray(program)) throw new Error('formato');
      const clean = program.map((d) => ({
        id: d.id || uid(),
        name: String(d.name || 'Scheda'),
        exercises: (d.exercises || []).map((e) => ({
          id: e.id || uid(),
          name: String(e.name || ''),
          sets: parseInt(e.sets, 10) || 3,
          reps: String(e.reps ?? '10'),
          rest: parseInt(e.rest, 10) || 90,
        })),
      }));
      update(() => ({
        program: clean,
        ...(Array.isArray(data.history) ? { history: data.history } : {}),
      }));
      setImporting(false);
      setImportText('');
      Alert.alert('Importato', `${clean.length} schede caricate.`);
    } catch {
      Alert.alert('JSON non valido', 'Incolla un JSON esportato dall\'app o una lista di schede.');
    }
  };

  return (
    <Screen>
      <Title sub="Le tue schede di allenamento">Programma</Title>

      {state.program.map((d) =>
        editing === d.id ? (
          <DayEditor
            key={d.id}
            day={d}
            onChange={(nd) => setProgram(state.program.map((x) => (x.id === d.id ? nd : x)))}
            onClose={() => setEditing(null)}
            onDelete={() =>
              Alert.alert('Eliminare la scheda?', d.name, [
                { text: 'No', style: 'cancel' },
                {
                  text: 'Elimina',
                  style: 'destructive',
                  onPress: () => {
                    setProgram(state.program.filter((x) => x.id !== d.id));
                    setEditing(null);
                  },
                },
              ])
            }
          />
        ) : (
          <Pressable key={d.id} onPress={() => setEditing(d.id)}>
            <Card>
              <View style={[s.row, { justifyContent: 'space-between' }]}>
                <T style={{ fontWeight: '800', fontSize: 17, flex: 1 }}>{d.name}</T>
                <Muted>Modifica ›</Muted>
              </View>
              {d.exercises.map((e) => (
                <View key={e.id} style={[s.row, { justifyContent: 'space-between', marginTop: 6 }]}>
                  <T style={{ fontSize: 15, flex: 1 }}>{e.name}</T>
                  <Muted>
                    {e.sets}×{e.reps} · {e.rest}s
                  </Muted>
                </View>
              ))}
            </Card>
          </Pressable>
        )
      )}

      <Btn
        kind="ghost"
        label="+ Nuova scheda"
        onPress={() => {
          const id = uid();
          setProgram([...state.program, { id, name: 'Nuova scheda', exercises: [] }]);
          setEditing(id);
        }}
      />

      <Muted style={{ marginTop: 24, marginBottom: 8, fontWeight: '700' }}>BACKUP</Muted>
      <View style={[s.row, { gap: 8 }]}>
        <Btn
          small
          kind="ghost"
          label="Esporta JSON"
          style={{ flex: 1 }}
          onPress={() =>
            Share.share({ message: JSON.stringify({ program: state.program, history: state.history }) })
          }
        />
        <Btn small kind="ghost" label="Importa JSON" style={{ flex: 1 }} onPress={() => setImporting((v) => !v)} />
      </View>
      {importing && (
        <Card style={{ marginTop: 12 }}>
          <Input
            value={importText}
            onChangeText={setImportText}
            multiline
            placeholder='{"program":[{"name":"Push","exercises":[{"name":"Panca","sets":4,"reps":"8","rest":120}]}]}'
            style={{ minHeight: 120, textAlignVertical: 'top', fontSize: 13 }}
          />
          <Btn small label="Importa" style={{ marginTop: 8 }} onPress={doImport} />
        </Card>
      )}
      <Btn
        small
        kind="danger"
        label="Ripristina programma di default"
        style={{ marginTop: 12 }}
        onPress={() =>
          Alert.alert('Ripristinare il programma?', 'Lo storico non viene toccato.', [
            { text: 'No', style: 'cancel' },
            { text: 'Ripristina', style: 'destructive', onPress: () => setProgram(DEFAULT_PROGRAM) },
          ])
        }
      />
    </Screen>
  );
}
