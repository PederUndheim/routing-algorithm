import pandas as pd

# === 1. Read the CSV ===
df = pd.read_csv("data/div/Snoskredulykker-tabell_2025-12-03 12-22-13.csv", sep=";")

# === 2. Clean column names ===
df.columns = df.columns.str.strip()

# === 3. Ensure the needed columns exist ===
required_cols = ["Døde", "Skredtype"]
missing = set(required_cols) - set(df.columns)
if missing:
    raise ValueError(f"Missing columns in CSV: {missing}")

# === 4. Convert values ===
df["Døde"] = pd.to_numeric(df["Døde"], errors="coerce").fillna(0).astype(int)
df["Skredtype"] = df["Skredtype"].astype(str).str.strip()

# === 5. Count deaths by avalanche type ===
deaths_per_type = (
    df.groupby("Skredtype")["Døde"]
      .sum()
      .sort_values(ascending=False)
)

print("Deaths per avalanche type:")
print(deaths_per_type)
