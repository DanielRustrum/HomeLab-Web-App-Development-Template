import { api } from 'tsunami'

export default function() {
    const note_234 = api("note.234.get")
    
    return (
        <p>{note_234.body}</p>
    )
}