export interface Note {
  id: NoteId;
  title: string;
  body: string;
  created_at: string;
}

export interface Notes {
  notes: Note[];
}

export type NoteId = number;

export interface NotesPostBody {
  note: Note;
  blank: number;
}

export type EndpointParams = {
  "notes.post": NotesPostBody;
}

export type Endpoints = {
  "notes.get": Notes;
  "notes.post": NotesPostBody;
}
