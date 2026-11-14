"""Who is connected to whom through played matches (ADR-0012). Pure: no I/O."""

from collections import Counter
from collections.abc import Iterable


class UnionFind:
    """Incremental connectivity; there are no deletions."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}
        self.size: dict[int, int] = {}

    def find(self, x: int) -> int:
        parent = self.parent
        if x not in parent:
            parent[x], self.size[x] = x, 1
            return x
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]

    def connected(self, a: int, b: int) -> bool:
        """False for a player never seen: they have no path to anyone yet."""
        return a in self.parent and b in self.parent and self.find(a) == self.find(b)


def components(edges: Iterable[tuple[int, int]]) -> list[int]:
    """Component sizes, largest first."""
    uf = UnionFind()
    for a, b in edges:
        uf.union(a, b)
    return sorted(Counter(uf.find(x) for x in uf.parent).values(), reverse=True)
