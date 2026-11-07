// Default program. Edit freely in the app (tab "Programma") or here.
// Each exercise: name, sets, reps (target, can be a range like "8-10"), rest (seconds).
export const DEFAULT_PROGRAM = [
  {
    id: 'push',
    name: 'Push – Petto / Spalle / Tricipiti',
    exercises: [
      { id: 'p1', name: 'Panca piana bilanciere', sets: 4, reps: '6-8', rest: 150 },
      { id: 'p2', name: 'Panca inclinata manubri', sets: 3, reps: '8-10', rest: 120 },
      { id: 'p3', name: 'Military press', sets: 3, reps: '6-8', rest: 120 },
      { id: 'p4', name: 'Alzate laterali', sets: 3, reps: '12-15', rest: 60 },
      { id: 'p5', name: 'Push-down ai cavi', sets: 3, reps: '10-12', rest: 60 },
    ],
  },
  {
    id: 'pull',
    name: 'Pull – Dorso / Bicipiti',
    exercises: [
      { id: 'l1', name: 'Stacco da terra', sets: 3, reps: '5', rest: 180 },
      { id: 'l2', name: 'Trazioni / Lat machine', sets: 4, reps: '8-10', rest: 120 },
      { id: 'l3', name: 'Rematore bilanciere', sets: 3, reps: '8-10', rest: 120 },
      { id: 'l4', name: 'Face pull', sets: 3, reps: '15', rest: 60 },
      { id: 'l5', name: 'Curl bilanciere', sets: 3, reps: '10-12', rest: 60 },
    ],
  },
  {
    id: 'legs',
    name: 'Legs – Gambe / Core',
    exercises: [
      { id: 'g1', name: 'Squat', sets: 4, reps: '6-8', rest: 180 },
      { id: 'g2', name: 'Stacco rumeno', sets: 3, reps: '8-10', rest: 120 },
      { id: 'g3', name: 'Leg press', sets: 3, reps: '10-12', rest: 120 },
      { id: 'g4', name: 'Leg curl', sets: 3, reps: '12', rest: 60 },
      { id: 'g5', name: 'Calf raise', sets: 4, reps: '12-15', rest: 60 },
      { id: 'g6', name: 'Plank (sec)', sets: 3, reps: '45', rest: 45 },
    ],
  },
];
