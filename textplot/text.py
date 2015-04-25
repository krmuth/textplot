

import os
import re
import matplotlib.pyplot as plt
import textplot.utils as utils
import numpy as np
import pkgutil

from nltk.stem import PorterStemmer
from sklearn.neighbors import KernelDensity
from collections import OrderedDict, Counter
from scipy.spatial import distance
from scipy import ndimage
from functools import lru_cache


class Text:


    @classmethod
    def from_file(cls, path):

        """
        Create a text from a file.

        Args:
            path (str): The file path.
        """

        return cls(open(path, 'r', errors='replace').read())


    def __init__(self, text):

        """
        Store the raw text, tokenize.

        Args:
            text (str): The raw text string.
        """

        self.text = text
        self.stem = PorterStemmer().stem
        self.tokenize()


    def stopwords(self, path='stopwords.txt'):

        """
        Load a set of stopwords.

        Args:
            path (str): The stopwords file path.

        Returns:
            set: Stopwords.
        """

        # Get an absolute path for the file.
        path = os.path.join(os.path.dirname(__file__), path)

        with open(path) as f:
            return set(f.read().splitlines())


    def tokenize(self):

        """
        Tokenize the text.
        """

        self.tokens = []
        self.terms = OrderedDict()

        # Load stopwords.
        stopwords = self.stopwords()

        # Generate tokens.
        for token in utils.tokenize(self.text):

            # Ignore stopwords.
            if token['unstemmed'] in stopwords:
                self.tokens.append(None)

            else:

                # Token:
                self.tokens.append(token)

                # Term:
                offsets = self.terms.setdefault(token['stemmed'], [])
                offsets.append(token['offset'])


    def term_counts(self):

        """
        Returns:
            OrderedDict: An ordered dictionary of term counts.
        """

        counts = OrderedDict()
        for term in self.terms:
            counts[term] = len(self.terms[term])

        return utils.sort_dict(counts)


    def term_count_buckets(self):

        """
        Returns:
            dict: A dictionary that maps occurrence counts to the terms that
            appear that many times in the text.
        """

        buckets = {}
        for term, count in self.term_counts().items():
            if count in buckets: buckets[count].append(term)
            else: buckets[count] = [term]

        return buckets


    def most_frequent_terms(self, depth):

        """
        Get the X most frequent terms in the text, and then probe down to get
        any other terms that have the same count as the last term.

        Args:
            depth (int): The number of terms.

        Returns:
            set: The set of frequent terms.
        """

        counts = self.term_counts()

        # Get the top X terms and the instance count of the last word.
        top_terms = set(list(counts.keys())[:depth])
        end_count = list(counts.values())[:depth][-1]

        # Merge in all other words with that appear that number of times, so
        # that we don't truncate the last bucket - eg, half of the words that
        # appear 5 times, but not the other half.

        bucket = self.term_count_buckets()[end_count]
        return top_terms.union(set(bucket))


    def term_distances(self, term):

        """
        Get a list of distances between the occurrences of a term.

        Args:
            term (str): A stemmed term.

        Returns:
            list: The interval distances.
        """

        distances = []
        for o1, o2 in utils.window(self.terms[term], 2):
            distances.append(o2-o1)

        return distances


    def unstem(self, term):

        """
        Given a stemmed term, get the most common unstemmed variant.

        Args:
            term (str): A stemmed term.

        Returns:
            str: The unstemmed token.
        """

        originals = []
        for i in self.terms[term]:
            originals.append(self.tokens[i]['unstemmed'])

        mode = Counter(originals).most_common(1)
        return mode[0][0]


    @lru_cache()
    def kde(self, term, bandwidth=2000, samples=1000, kernel='gaussian'):

        """
        Estimate the kernel density of the instances of term in the text.

        Args:
            term (str): A stemmed term.
            bandwidth (int): The kernel bandwidth.
            samples (int): The number of evenly-spaced sample points.
            kernel (str): The kernel function.

        Returns:
            np.array: The density estimate.
        """

        # Get the offsets of the term instances.
        terms = np.array(self.terms[term])[:, np.newaxis]

        # Fit the density estimator on the terms.
        kde = KernelDensity(kernel=kernel, bandwidth=bandwidth).fit(terms)

        # Score an evely-spaced array of samples.
        x_axis = np.linspace(0, len(self.tokens), samples)[:, np.newaxis]
        scores = kde.score_samples(x_axis)

        # Scale the scores to integrate to 1.
        return np.exp(scores) * (len(self.tokens) / samples)


    def score_intersect(self, term1, term2, **kwargs):

        """
        Compute the geometric area of the overlap between the kernel density
        estimates of two terms.

        Args:
            term1 (str)
            term1 (str)

        Returns: float
        """

        t1_kde = self.kde(term1, **kwargs)
        t2_kde = self.kde(term2, **kwargs)

        # Integrate the overlap.
        overlap = np.minimum(t1_kde, t2_kde)
        return np.trapz(overlap)


    def score_cosine(self, term1, term2, **kwargs):

        """
        Compute a weighting score based on the cosine distance between the
        kernel density estimates of two terms.

        Args:
            term1 (str)
            term1 (str)

        Returns: float
        """

        t1_kde = self.kde(term1, **kwargs)
        t2_kde = self.kde(term2, **kwargs)

        return 1-distance.cosine(t1_kde, t2_kde)


    def score_braycurtis(self, term1, term2, **kwargs):

        """
        Compute a weighting score based on the "City Block" distance between
        the kernel density estimates of two terms.

        Args:
            term1 (str)
            term1 (str)

        Returns: float
        """

        t1_kde = self.kde(term1, **kwargs)
        t2_kde = self.kde(term2, **kwargs)

        return 1-distance.braycurtis(t1_kde, t2_kde)


    def anchored_scores(self, anchor, method='braycurtis', **kwargs):

        """
        Compute the intersections between an anchor term and all other terms.

        Args:
            anchor (str): The anchor term.
            method (str): The scoring function.

        Returns:
            OrderedDict: Distances between the anchor and all other terms.
        """

        evaluator = getattr(self, 'score_'+method)

        pairs = OrderedDict()
        for term in self.terms:
            pairs[term] = evaluator(anchor, term, **kwargs)

        return utils.sort_dict(pairs)


    def plot_term_kdes(self, words, **kwargs):

        """
        Plot kernel density estimates for multiple words.

        :param words: The words to query.
        :param bandwidth: The kernel width.
        """

        for word in words:
            kde = self.kde(self.stem(word), **kwargs)
            plt.plot(kde)

        plt.show()
