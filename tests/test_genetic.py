import numpy as np
import unittest
import gnas


class TestGenetic(unittest.TestCase):

    def test_search_cnn_space(self):
        ss = gnas.get_enas_cnn_search_space(5, 1, gnas.SearchSpaceType.CNNSingleCell)
        ga = gnas.genetic_algorithm_searcher(ss, population_size=200, generation_size=20)
        for i in range(30):
            for i, ind in enumerate(ga.get_current_generation()):
                ga.sample_child()
                ga.update_current_individual_fitness(ind, 0 + np.random.rand(1))
            ga.update_population()
            # print(len(ga.max_dict))
            self.assertTrue(len(ga.max_dict) <= 200)
            self.assertTrue(len(ga.generation))


if __name__ == '__main__':
    unittest.main()
