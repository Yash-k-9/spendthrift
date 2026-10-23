"""Genetic Algorithm (from scratch), for continuous optimisation.

A chromosome is a vector of genes, each within [lower, upper]. Each generation:
  1. fitness   - score every chromosome (higher is better)
  2. elitism   - copy the best few unchanged into the next generation
  3. selection - tournament: pick 3 at random, the fittest becomes a parent
  4. crossover - blend two parents gene by gene: child = a*p1 + (1-a)*p2
  5. mutation  - with a small probability, nudge a gene by Gaussian noise
Repeat for a number of generations; return the best chromosome found.
"""

import numpy as np


def genetic_optimize(fitness, lower, upper, pop_size: int = 80, generations: int = 150,
                     crossover_rate: float = 0.9, mutation_rate: float = 0.15, mutation_scale: float = 0.1,
                     elite: int = 2, tournament: int = 3, seed: int = 0):
    """fitness(population) takes a (pop_size, n_genes) array and returns (pop_size,) scores.

    Returns (best_chromosome, best_fitness, history) where history is the best
    fitness of each generation (for a convergence chart).
    """
    rng = np.random.default_rng(seed)
    lower, upper = np.asarray(lower, float), np.asarray(upper, float)
    span = upper - lower
    pop = lower + rng.random((pop_size, len(lower))) * span
    history = []

    for _ in range(generations):
        scores = fitness(pop)
        order = np.argsort(-scores)
        history.append(float(scores[order[0]]))
        next_pop = [pop[i].copy() for i in order[:elite]]

        while len(next_pop) < pop_size:
            parents = []
            for _ in range(2):
                contenders = rng.integers(pop_size, size=tournament)
                parents.append(pop[contenders[np.argmax(scores[contenders])]])
            child = parents[0].copy()
            if rng.random() < crossover_rate:
                alpha = rng.random(len(lower))
                child = alpha * parents[0] + (1 - alpha) * parents[1]
            mutate = rng.random(len(lower)) < mutation_rate
            child = child + mutate * rng.normal(0, mutation_scale, len(lower)) * span
            next_pop.append(np.clip(child, lower, upper))
        pop = np.array(next_pop)

    scores = fitness(pop)
    best = int(np.argmax(scores))
    return pop[best], float(scores[best]), history
