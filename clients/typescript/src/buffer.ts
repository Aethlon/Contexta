interface QueuedEntry {
  id: string;
  url: string;
  body: string;
  headers: Record<string, string>;
  timestamp: number;
  retries: number;
}

interface NodeFs {
  existsSync(path: string): boolean;
  readFileSync(path: string, encoding: string): string;
  writeFileSync(path: string, data: string, encoding: string): void;
  mkdirSync(path: string, options: { recursive: boolean }): void;
}

interface NodePath {
  join(...parts: string[]): string;
}

interface NodeOs {
  tmpdir(): string;
}

type StorageBackend = "memory" | "localStorage" | "node";

export class DurableBuffer {
  private maxSize: number;
  private maxRetries: number;
  private backend: StorageBackend = "memory";
  private storage: Storage | null = null;
  private fs: NodeFs | null = null;
  private fsPath: string | null = null;
  private memory: QueuedEntry[] = [];
  private initPromise: Promise<void>;

  constructor(maxSize = 1000, maxRetries = 5) {
    this.maxSize = maxSize;
    this.maxRetries = maxRetries;
    this.initPromise = this.initialize();
  }

  private async initialize(): Promise<void> {
    if (typeof window !== "undefined" && window.localStorage) {
      this.storage = window.localStorage;
      this.backend = "localStorage";
    } else if (typeof process !== "undefined" && process.versions?.node) {
      try {
        const fs = await this.importNodeFs();
        const path = await this.importNodePath();
        const os = await this.importNodeOs();
        if (fs && path && os) {
          this.fs = fs;
          this.fsPath = path.join(os.tmpdir(), "contexta-buffer.json");
          this.backend = "node";
        }
      } catch {
        this.backend = "memory";
      }
    }
    await this.load();
  }

  async waitForInit(): Promise<void> {
    await this.initPromise;
  }

  async push(url: string, body: string, headers: Record<string, string>): Promise<void> {
    await this.initPromise;
    const entry: QueuedEntry = {
      id: crypto.randomUUID(),
      url,
      body,
      headers,
      timestamp: Date.now(),
      retries: 0,
    };

    this.memory.push(entry);

    if (this.memory.length > this.maxSize) {
      const rotated = this.memory.splice(0, this.memory.length - this.maxSize);
      await this.persistDeadLetter(rotated);
    }

    await this.persist();
  }

  async pop(): Promise<QueuedEntry | null> {
    await this.initPromise;
    return this.memory.shift() ?? null;
  }

  async requeue(entry: QueuedEntry): Promise<void> {
    await this.initPromise;
    entry.retries++;
    if (entry.retries >= this.maxRetries) {
      await this.persistDeadLetter([entry]);
      return;
    }
    entry.timestamp = Date.now();
    this.memory.push(entry);
    await this.persist();
  }

  get length(): number {
    return this.memory.length;
  }

  async flush(): Promise<void> {
    await this.initPromise;
    this.memory = [];
    await this.persist();
  }

  private async load(): Promise<void> {
    if (this.backend === "localStorage" && this.storage) {
      const raw = this.storage.getItem("CONTEXTA_buffer");
      if (raw) {
        try {
          this.memory = JSON.parse(raw);
        } catch {
          this.memory = [];
        }
      }
    } else if (this.backend === "node" && this.fs && this.fsPath) {
      try {
        if (this.fs.existsSync(this.fsPath)) {
          const raw = this.fs.readFileSync(this.fsPath, "utf-8");
          this.memory = JSON.parse(raw);
        }
      } catch {
        this.memory = [];
      }
    }
  }

  private async persist(): Promise<void> {
    const raw = JSON.stringify(this.memory);
    if (this.backend === "localStorage" && this.storage) {
      this.storage.setItem("CONTEXTA_buffer", raw);
    } else if (this.backend === "node" && this.fs && this.fsPath) {
      try {
        this.fs.writeFileSync(this.fsPath, raw, "utf-8");
      } catch {
      }
    }
  }

  private async persistDeadLetter(entries: QueuedEntry[]): Promise<void> {
    const key = "CONTEXTA_dead_letter";
    const raw = JSON.stringify(entries);
    if (this.backend === "localStorage" && this.storage) {
      const existing = this.storage.getItem(key);
      const all = existing ? [...JSON.parse(existing), ...entries] : entries;
      this.storage.setItem(key, JSON.stringify(all));
    } else if (this.backend === "node" && this.fs && this.fsPath) {
      try {
        const dlPath = this.fsPath.replace(".json", "-dead-letter.json");
        const existing = this.fs.existsSync(dlPath)
          ? JSON.parse(this.fs.readFileSync(dlPath, "utf-8"))
          : [];
        this.fs.writeFileSync(dlPath, JSON.stringify([...existing, ...entries]), "utf-8");
      } catch {
      }
    }
  }

  private async importNodeFs(): Promise<NodeFs | null> {
    try {
      const mod = await import("fs");
      return mod as unknown as NodeFs;
    } catch {
      return null;
    }
  }

  private async importNodePath(): Promise<NodePath | null> {
    try {
      const mod = await import("path");
      return mod as unknown as NodePath;
    } catch {
      return null;
    }
  }

  private async importNodeOs(): Promise<NodeOs | null> {
    try {
      const mod = await import("os");
      return mod as unknown as NodeOs;
    } catch {
      return null;
    }
  }
}
