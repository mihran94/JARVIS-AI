"""JARVIS Blue V73.1 desktop prototype; no microphone, automation or code execution."""
import os
import threading
import tkinter as tk
from tkinter import ttk
from core import ollama_chat, provider_statuses, ollama_health

BG = '#07111e'
PANEL = '#10243a'
FG = '#d7f4ff'
BLUE = '#39caff'

def main():
    root = tk.Tk()
    root.title('JARVIS BLUE — Quantum Command Center (Early Access)')
    root.geometry('920x640')
    root.configure(bg=BG)
    tk.Label(root, text='J A R V I S   B L U E', font=('Segoe UI', 26, 'bold'), bg=BG, fg=BLUE).pack(pady=(22, 2))
    tk.Label(root, text='QUANTUM COMMAND CENTER  •  LOCAL-FIRST  •  SAFE MODE', bg=BG, fg=FG).pack(pady=(0, 16))
    status = tk.StringVar(value='Ready — No automatic commands or microphone access')
    tk.Label(root, textvariable=status, bg=BG, fg=BLUE).pack(pady=4)
    providers = '    |    '.join(f'{p.name}: {"configured" if p.configured else "not configured"}' for p in provider_statuses(os.environ))
    tk.Label(root, text=providers, bg=BG, fg=FG, wraplength=860).pack(pady=8)
    output = tk.Text(root, bg=PANEL, fg=FG, insertbackground=FG, relief='flat', font=('Consolas', 11), wrap='word', height=18)
    output.pack(fill='both', expand=True, padx=22, pady=12)
    output.insert('end', 'JARVIS Blue ready. Local Ollama chat only.\nCloud providers are status-only in this build.\n\n')
    output.configure(state='disabled')
    entry = ttk.Entry(root, font=('Segoe UI', 12))
    entry.pack(fill='x', padx=22, pady=5)
    model = tk.StringVar(value='llama3.2')
    bottom = tk.Frame(root, bg=BG)
    bottom.pack(fill='x', padx=22, pady=(4, 18))
    tk.Label(bottom, text='Ollama model:', bg=BG, fg=FG).pack(side='left')
    ttk.Entry(bottom, textvariable=model, width=17).pack(side='left', padx=8)
    send = ttk.Button(bottom, text='Ask local Ollama')
    send.pack(side='left', padx=10)
    tk.Label(bottom, text='Wake word OFF   •   Automation OFF   •   Approval required', bg=BG, fg=BLUE).pack(side='right')

    def append(message):
        output.configure(state='normal')
        output.insert('end', message + '\n')
        output.see('end')
        output.configure(state='disabled')

    def send_message():
        prompt = entry.get().strip()
        if not prompt:
            return
        selected_model = model.get()
        entry.delete(0, 'end')
        append('YOU: ' + prompt)
        status.set('Waiting for local Ollama...')
        send.configure(state='disabled')
        def worker():
            try:
                msg = 'JARVIS: ' + ollama_chat(prompt, model=selected_model)
            except Exception as exc:
                msg = 'Local Ollama unavailable: ' + str(exc)
            def finish():
                append(msg + '\n')
                status.set('Ready — Safe mode')
                send.configure(state='normal')
            root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def check_ollama():
        status.set('Checking local Ollama...')
        health.configure(state='disabled')
        def worker():
            healthy = ollama_health()
            root.after(0, lambda: finish_health(healthy))
        threading.Thread(target=worker, daemon=True).start()

    def finish_health(healthy):
        status.set('Ollama reachable' if healthy else 'Ollama offline — dashboard remains available')
        health.configure(state='normal')

    health = ttk.Button(bottom, text='Check Ollama', command=check_ollama)
    health.pack(side='left', padx=4)
    send.configure(command=send_message)
    entry.bind('<Return>', lambda _event: send_message())
    root.mainloop()

if __name__ == '__main__':
    main()
