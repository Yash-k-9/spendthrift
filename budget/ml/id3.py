"""ID3 Decision Tree (from scratch).

Builds the tree top-down. At each node:
  1. Entropy(S) = -sum p_c * log2(p_c)           (how mixed the labels are)
  2. Gain(S, A) = Entropy(S) - sum |S_v|/|S| * Entropy(S_v)
     for every attribute A, where S_v = examples with A = v
  3. split on the attribute with the highest information gain
  4. recurse on each branch until the node is pure or no attributes remain

All attributes are categorical. Examples can carry weights (a family's own
labels count more than the built-in expert examples).
"""

import math
from collections import defaultdict


def entropy(weights_by_label: dict) -> float:
    total = sum(weights_by_label.values())
    return -sum((w / total) * math.log2(w / total) for w in weights_by_label.values() if w > 0)


class ID3DecisionTree:
    def __init__(self, max_depth: int = 6):
        self.max_depth = max_depth

    def fit(self, rows: list[dict], labels: list[str], attributes: list[str], weights=None) -> "ID3DecisionTree":
        weights = weights or [1.0] * len(rows)
        self.attributes = attributes
        self.values = {a: sorted({r[a] for r in rows}) for a in attributes}
        self.tree = self._build(list(zip(rows, labels, weights)), list(attributes), depth=0)
        return self

    @staticmethod
    def _label_weights(examples) -> dict:
        counts = defaultdict(float)
        for _, label, w in examples:
            counts[label] += w
        return dict(counts)

    def information_gain(self, examples, attribute) -> float:
        total = sum(w for _, _, w in examples)
        split = defaultdict(list)
        for ex in examples:
            split[ex[0][attribute]].append(ex)
        remainder = sum(sum(w for _, _, w in subset) / total * entropy(self._label_weights(subset))
                        for subset in split.values())
        return entropy(self._label_weights(examples)) - remainder

    def _build(self, examples, attributes, depth):
        counts = self._label_weights(examples)
        majority = max(counts, key=counts.get)
        if len(counts) == 1 or not attributes or depth >= self.max_depth:
            return {"leaf": majority, "counts": counts}
        gains = {a: self.information_gain(examples, a) for a in attributes}
        best = max(gains, key=gains.get)
        if gains[best] <= 1e-9:
            return {"leaf": majority, "counts": counts}
        node = {"attribute": best, "gain": gains[best], "majority": majority, "children": {}}
        remaining = [a for a in attributes if a != best]
        for value in self.values[best]:
            subset = [ex for ex in examples if ex[0][best] == value]
            node["children"][value] = (self._build(subset, remaining, depth + 1) if subset
                                       else {"leaf": majority, "counts": {}})
        return node

    def predict(self, row: dict) -> tuple[str, list[tuple[str, str]]]:
        """Returns (label, decision path as [(attribute, value), ...])."""
        node, path = self.tree, []
        while "leaf" not in node:
            value = row[node["attribute"]]
            path.append((node["attribute"], value))
            node = node["children"].get(value, {"leaf": node["majority"]})
        return node["leaf"], path

    def rules(self) -> list[str]:
        """The tree as readable IF ... THEN ... rules."""
        out = []

        def walk(node, conditions):
            if "leaf" in node:
                if node["counts"]:  # skip branches no training example reached
                    cond = " AND ".join(f"{a} = {v}" for a, v in conditions) or "always"
                    out.append(f"IF {cond} THEN {node['leaf']}")
                return
            for value, child in node["children"].items():
                walk(child, conditions + [(node["attribute"], value)])

        walk(self.tree, [])
        return out

    def depth(self, node=None) -> int:
        node = node or self.tree
        return 0 if "leaf" in node else 1 + max(self.depth(c) for c in node["children"].values())
