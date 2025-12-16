export interface Note {
  id: number;
  title: string;
  body: string;
  created_at: string;
}

export interface Notes {
  notes: Note[];
}

export interface Test {
  name: string;
  age: number;
}

export interface Potota {
  typr: string;
}

export interface Tomato {
  name: string;
  age: number;
  test: Potota;
}

export type Endpoints = {
  "notes": Notes;
  "test": Test;
  "test1": Tomato;
}
