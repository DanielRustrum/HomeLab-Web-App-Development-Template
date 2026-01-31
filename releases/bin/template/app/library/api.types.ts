import { struct } from "tsunami";


interface NoteNoteIdPostBodyObject {
  note: unknown;
}
export const NoteNoteIdPostBody = struct<NoteNoteIdPostBodyObject>()("note");
export type NoteNoteIdPostBody = NoteNoteIdPostBodyObject;


type StaticEndpointSpec = {
}


type DynamicEndpointCases = [
  { pattern: `notebook.${string}.get`; response: Notes; body: never; query: never; path: { book_id: string } },
  { pattern: `note.${string}.post`; response: NoteNoteIdPostBody; body: NoteNoteIdPostBody; query: never; path: { note_id: string } },
  { pattern: `note.${string}.get`; response: unknown; body: never; query: never; path: { note_id: string } },
]


type DefaultEndpointSpec = { response: unknown; body: never; query: never; path: never };

type MatchDynamicSpec<Key extends string, Cases extends readonly unknown[]> =
  Cases extends readonly [infer Head, ...infer Tail extends readonly unknown[]]
    ? Head extends { pattern: infer Pattern }
      ? Pattern extends string
        ? Key extends Pattern
          ? Head
          : MatchDynamicSpec<Key, Tail>
        : DefaultEndpointSpec
      : DefaultEndpointSpec
    : DefaultEndpointSpec;


export type EndpointKey = keyof StaticEndpointSpec | DynamicEndpointCases[number]['pattern'];

type EndpointSpecFor<Key extends EndpointKey> =
  Key extends keyof StaticEndpointSpec
    ? StaticEndpointSpec[Key]
    : MatchDynamicSpec<Key, DynamicEndpointCases>;


export type Endpoints = { [Key in EndpointKey]: EndpointSpecFor<Key>['response'] };
export type EndpointParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['body'] };
export type EndpointQueryParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['query'] };
export type EndpointPathParams = { [Key in EndpointKey]: EndpointSpecFor<Key>['path'] };


export type EndpointSpec<K extends EndpointKey> = EndpointSpecFor<K>;
export type EndpointResponse<K extends EndpointKey> = EndpointSpecFor<K>["response"];
export type EndpointBody<K extends EndpointKey> = EndpointSpecFor<K>["body"];
export type EndpointQuery<K extends EndpointKey> = EndpointSpecFor<K>["query"];
export type EndpointPath<K extends EndpointKey> = EndpointSpecFor<K>["path"];


type __TsunamiEndpointSpecMap = { [K in EndpointKey]: EndpointSpec<K> };

declare module "tsunami" {
  interface EndpointSpecMap extends __TsunamiEndpointSpecMap {}
}
