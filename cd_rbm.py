#!/usr/bin/env python

"""
CD for RBM

*Reference*
Geoffrey E. Hinton. Training Products of Experts by Minimizing Contrastive Divergence.
Miguel A. Carreira-Perpinnaan, Geoffrey E. Hinton. On Contrastive Divergence Learning.

"""

import numpy as np
import numpy.linalg as LA
import random
from scipy.stats import rv_discrete, multivariate_normal, bernoulli
from scipy.special import expit, softmax
from sklearn.base import TransformerMixin



def gibbs(x, W, nx, mc_iter=1):
    """Gibbs sampling
    """
    p, r = W.shape

    pz = expit(np.dot(x, W))
    z = np.random.random(r) < pz
    x[-1] = z[-1] = pz[-1] = 1
    for _ in range(mc_iter):
        ps = np.cumsum(softmax(np.column_stack([x * np.dot(W, z) for x in range(nx)]), axis=1), axis=1)
        rv = np.random.random(p)
        # x1 = [np.where(rvi<pi)[0][0] for rvi, pi in zip(rv, ps)]
        x1 = np.array([np.where(k)[0][0] for k in (rv[:,None] < ps)])
        # np.array([rv_discrete(values=(xs, softmax([x * np.dot(W[j,:], z) for x in xs]))).rvs() for j in range(p)])
        pz1 = expit(np.dot(x1, W))
        z = np.random.random(r) < pz1
        x1[-1] = z[-1] = pz1[-1] = 1
    return x1, pz, pz1

def binary_gibbs(x, W, mc_iter=1):
    """Gibbs sampling
    """
    p, r = W.shape

    pz = expit(np.dot(x, W))
    z = np.random.random(r) < pz
    x[-1] = z[-1] = pz[-1] = 1
    for _ in range(mc_iter):
        px = expit(np.dot(W, z))
        x1 = np.random.random(p) < px
        pz1 = expit(np.dot(x1, W))
        z = np.random.random(r) < pz1
        x1[-1] = z[-1] = pz1[-1] = 1
    return x1, pz, pz1


class CDRBM(TransformerMixin):
    """
    Restricted Boltzmann Machine by Contrastive Divergence

    Example:

        from sklearn import datasets

        digists = datasets.load_digits()
        X_train, y_train = digists.data, digists.target

        X = X_train[y_train==0]

        rbm = CDRBM(max_iter=500, mc_iter=1, persistent=False)
        # number of values taken by x, {0,1,...16}
        rbm.n_values = 17 # currently, you have to set the attr. manually.
        rbm.fit(X)

        x = rbm.generate(mc_iter=50)
    """
    def __init__(self, ndim_latens=3, max_iter=500, mc_iter=1, persistent=True, bias=True):
        """CD-RBM
        
        Args:
            ndim_latens (int, optional): dim. of laten var.
            max_iter (int, optional): iterations
            mc_iter (int, optional): length of Markov chain/ iterations of Gibbs sampling
            persistent (bool, optional): for PCD
            bias (bool): True by default
        """
        self.max_iter = max_iter
        self.mc_iter = mc_iter
        self.persistent = persistent
        self.ndim_latens = ndim_latens
        self.bias = bias
        self.n_values = 2

    def grad_energy(self, x, z):
        return np.outer(x, z)


    def init(self, X):
        if self.bias:
            X = np.insert(X, -1, 1, axis=1)
        n_samples, self.n_features_ = X.shape
        self.weight_ = np.zeros((self.n_features_, self.ndim_latens))
        return X


    def mcmc(self, x, mc_iter=None):
        return gibbs(x, self.weight_, self.n_values, mc_iter or self.mc_iter)


    def transform(self, X):
        return np.row_stack([np.random.random(self.ndim_latens) < expit(np.dot(x1, W)) for x1 in X])

    def inverse_transform(self, Z):
        def _it(z):
            ps = np.cumsum(softmax(np.column_stack([x * np.dot(W, z) for x in range(self.n_values)]), axis=1), axis=1)
            rv = np.random.random(p)
            return [np.where(k)[0][0] for k in (rv[:,None] < ps)]
        return np.array([_it(z) for z in Z])


    def fit(self, X):
        X = self.init(X)
        self._fit(X, self.max_iter, self.mc_iter, self.persistent)
        return self


    def _fit(self, X, max_iter=500, mc_iter=1, persistent=True):
        """CD k(==1) algo.

        mc_iter: iterations of mcmc
        persistent: for persistent CD
        """
        tol = 1e-7
        eta = 0.1
        n_samples, _ = X.shape
        
        n_batchs = 8

        if persistent:
            X = X.copy()

        for _ in range(self.max_iter):
            # index = np.random.random(n_samples)<0.2
            for n in range(n_batchs):
                index = np.random.choice(n_samples, int(n_samples//n_batchs))
                X_batch = X[index]
                XZ1 = [self.mcmc(x) for x in X_batch]
                positive = np.mean([np.outer(x, pz) for x, (_, pz, _) in zip(X_batch, XZ1)], axis=0)
                negative = np.mean([np.outer(x, pz1) for x, _, pz1 in XZ1], axis=0)
                DW = positive - negative

                if persistent:
                    X[index] = np.array([x for x, _, _ in XZ1])
                # if LA.norm(DW)<tol: break
                eta *= 0.99
                self.weight_ += eta * DW

    def generate(self, mc_iter=30, n_samples=None):
        x0 = np.random.randint(self.n_values, size=rbm.n_features_)
        x0[-1] =1
        x_, _, _ = self.mcmc(x0, mc_iter)
        return x_[:-1]


class BinaryCDRBM(CDRBM):
    """
    Binary RBM by CD

    Example:

        from sklearn import datasets

        digists = datasets.load_digits()
        X_train, y_train = digists.data, digists.target

        X_train = X_train[y_train==0]

        # binarize
        X = (X_train>8).astype(np.int_)

        rbm = BinaryCDRBM(max_iter=500, mc_iter=1, persistent=False)
        rbm.fit(X)

        # choose a sample
        x = X[4]
        xx = rbm.generate(mc_iter=30)
    """
    def mcmc(self, x, mc_iter=None):
        return binary_gibbs(x, self.weight_, mc_iter or self.mc_iter)

    def inverse_transform(self, Z):
        return np.row_stack([np.random.random(self.n_features_) < expit(np.dot(W, z)) for z in Z])


    def generate(self, mc_iter=30, n_samples=None):
        x0 = bernoulli(0.5).rvs(size=self.n_features_)
        x0[-1] =1
        x_, _, _ = self.mcmc(x0, mc_iter)
        return x_[:-1]


if __name__ == '__main__':
    
    from sklearn import datasets

    digists = datasets.load_digits()
    X_train, y_train = digists.data, digists.target

    X = X_train[y_train==0]

    rbm = CDRBM(max_iter=500, mc_iter=1, persistent=False)
    # number of values taken by x, {0,1,...16}
    rbm.n_values = 17 # currently, you have to set the attr. manually.
    rbm.fit(X)

    # choose a sample
    x = X[4]
    x_ = rbm.generate(mc_iter=50)

    import matplotlib.pyplot as plt
    fig = plt.figure()
    ax = fig.subplots(1, 2)
    ax[0].imshow(x.reshape((8, 8)))
    ax[0].set_title('A real digit')
    ax[1].imshow(x_.reshape((8, 8)))
    ax[1].set_title('generated by CD')
    for _ in ax: _.set_axis_off()
    fig.suptitle("Digit Generator (Test of CD-RBM)")
    plt.show()

