"""numerical differentiation function, gradient, Jacobian, and Hessian

Author : josef-pkt
License : BSD

Notes
-----
These are simple forward differentiation, so that we have them available
without dependencies.

* Jacobian should be faster than numdifftools because it doesn't use loop over
  observations.
* numerical precision will vary and depend on the choice of stepsizes
"""

# TODO:
# * some cleanup
# * check numerical accuracy (and bugs) with numdifftools and analytical
#   derivatives
#   - linear least squares case: (hess - 2*X'X) is 1e-8 or so
#   - gradient and Hessian agree with numdifftools when evaluated away from
#     minimum
#   - forward gradient, Jacobian evaluated at minimum is inaccurate, centered
#     (+/- epsilon) is ok
# * dot product of Jacobian is different from Hessian, either wrong example or
#   a bug (unlikely), or a real difference
#
#
# What are the conditions that Jacobian dotproduct and Hessian are the same?
#
# See also:
#
# BHHH: Greene p481 17.4.6,  MLE Jacobian = d loglike / d beta , where loglike
# is vector for each observation
#    see also example 17.4 when J'J is very different from Hessian
#    also does it hold only at the minimum, what's relationship to covariance
#    of Jacobian matrix
# http://projects.scipy.org/scipy/ticket/1157
# http://en.wikipedia.org/wiki/Levenberg%E2%80%93Marquardt_algorithm
#    objective: sum((y-f(beta,x)**2),   Jacobian = d f/d beta
#    and not d objective/d beta as in MLE Greene
#    similar: http://crsouza.blogspot.com/2009/11/neural-network-learning-by-levenberg_18.html#hessian
#
# in example: if J = d x*beta / d beta then J'J == X'X
#    similar to http://en.wikipedia.org/wiki/Levenberg%E2%80%93Marquardt_algorithm
from __future__ import print_function
from statsmodels.compat.python import range
import numpy as np

# NOTE: we only do double precision internally so far
EPS = np.MachAr().eps

_hessian_docs = """
    Calculate Hessian with finite difference derivative approximation

    Parameters
    ----------
    x : array_like
       value at which function derivative is evaluated
    f : function
       function of one array f(x, `*args`, `**kwargs`)
    epsilon : float or array-like, optional
       Stepsize used, if None, then stepsize is automatically chosen
       according to EPS**(1/%(scale)s)*x.
    args : tuple
        Arguments for function `f`.
    kwargs : dict
        Keyword arguments for function `f`.
    %(extra_params)s

    Returns
    -------
    hess : ndarray
       array of partial second derivatives, Hessian
    %(extra_returns)s

    Notes
    -----
    Equation (%(equation_number)s) in Ridout. Computes the Hessian as::

      %(equation)s

    where e[j] is a vector with element j == 1 and the rest are zero and
    d[i] is epsilon[i].

    References
    ----------:

    Ridout, M.S. (2009) Statistical applications of the complex-step method
        of numerical differentiation. The American Statistician, 63, 66-74
"""


def _get_epsilon(x, s, epsilon, n):
    if epsilon is None:
        h = EPS**(1. / s) * np.maximum(np.abs(x), 0.1)
    else:
        if np.isscalar(epsilon):
            h = np.empty(n)
            h.fill(epsilon)
        else:  # pragma : no cover
            h = np.asarray(epsilon)
            if h.shape != x.shape:
                raise ValueError("If h is not a scalar it must have the same"
                                 " shape as x.")
    return h


def approx_fprime(x, f, epsilon=None, args=(), kwargs={}, centered=False):
    '''
    Gradient of function, or Jacobian if function f returns 1d array

    Parameters
    ----------
    x : array
        parameters at which the derivative is evaluated
    f : function
        `f(*((x,)+args), **kwargs)` returning either one value or 1d array
    epsilon : float, optional
        Stepsize, if None, optimal stepsize is used. This is EPS**(1/2)*x for
        `centered` == False and EPS**(1/3)*x for `centered` == True.
    args : tuple
        Tuple of additional arguments for function `f`.
    kwargs : dict
        Dictionary of additional keyword arguments for function `f`.
    centered : bool
        Whether central difference should be returned. If not, does forward
        differencing.

    Returns
    -------
    grad : array
        gradient or Jacobian

    Notes
    -----
    If f returns a 1d array, it returns a Jacobian. If a 2d array is returned
    by f (e.g., with a value for each observation), it returns a 3d array
    with the Jacobian of each observation with shape xk x nobs x xk. I.e.,
    the Jacobian of the first observation would be [:, 0, :]
    '''
    n = len(x)
    # TODO:  add scaled stepsize
    f0 = f(*((x,)+args), **kwargs)
    dim = np.atleast_1d(f0).shape  # it could be a scalar
    grad = np.zeros((n,) + dim, float)
    ei = np.zeros((n,), float)
    if not centered:
        epsilon = _get_epsilon(x, 2, epsilon, n)
        for k in range(n):
            ei[k] = epsilon[k]
            grad[k, :] = (f(*((x+ei,) + args), **kwargs) - f0)/epsilon[k]
            ei[k] = 0.0
    else:
        epsilon = _get_epsilon(x, 3, epsilon, n) / 2.
        for k in range(len(x)):
            ei[k] = epsilon[k]
            grad[k, :] = (f(*((x+ei,)+args), **kwargs) -
                          f(*((x-ei,)+args), **kwargs))/(2 * epsilon[k])
            ei[k] = 0.0
    return grad.squeeze().T


def approx_fprime_cs(x, f, epsilon=None, args=(), kwargs={}):
    '''
    Calculate gradient or Jacobian with complex step derivative approximation

    Parameters
    ----------
    x : array
        parameters at which the derivative is evaluated
    f : function
        `f(*((x,)+args), **kwargs)` returning either one value or 1d array
    epsilon : float, optional
        Stepsize, if None, optimal stepsize is used. Optimal step-size is
        EPS*x. See note.
    args : tuple
        Tuple of additional arguments for function `f`.
    kwargs : dict
        Dictionary of additional keyword arguments for function `f`.

    Returns
    -------
    partials : ndarray
       array of partial derivatives, Gradient or Jacobian

    Notes
    -----
    The complex-step derivative has truncation error O(epsilon**2), so
    truncation error can be eliminated by choosing epsilon to be very small.
    The complex-step derivative avoids the problem of round-off error with
    small epsilon because there is no subtraction.
    '''
    # From Guilherme P. de Freitas, numpy mailing list
    # May 04 2010 thread "Improvement of performance"
    # http://mail.scipy.org/pipermail/numpy-discussion/2010-May/050250.html
    n = len(x)
    epsilon = _get_epsilon(x, 1, epsilon, n)
    increments = np.identity(n) * 1j * epsilon
    # TODO: see if this can be vectorized, but usually dim is small
    partials = [f(x+ih, *args, **kwargs).imag / epsilon[i]
                for i, ih in enumerate(increments)]
    return np.array(partials).T


def approx_hess_cs(x, f, epsilon=None, args=(), kwargs={}):
    '''Calculate Hessian with complex-step derivative approximation

    Parameters
    ----------
    x : array_like
       value at which function derivative is evaluated
    f : function
       function of one array f(x)
    epsilon : float
       stepsize, if None, then stepsize is automatically chosen

    Returns
    -------
    hess : ndarray
       array of partial second derivatives, Hessian

    Notes
    -----
    based on equation 10 in
    M. S. RIDOUT: Statistical Applications of the Complex-step Method
    of Numerical Differentiation, University of Kent, Canterbury, Kent, U.K.

    The stepsize is the same for the complex and the finite difference part.
    '''
    # TODO: might want to consider lowering the step for pure derivatives
    n = len(x)
    h = _get_epsilon(x, 3, epsilon, n)
    ee = np.diag(h)
    hess = np.outer(h, h)

    n = len(x)

    for i in range(n):
        for j in range(i, n):
            hess[i, j] = (f(*((x + 1j*ee[i, :] + ee[j, :],) + args), **kwargs)
                          - f(*((x + 1j*ee[i, :] - ee[j, :],)+args),
                              **kwargs)).imag/2./hess[i, j]
            hess[j, i] = hess[i, j]

    return hess
approx_hess_cs.__doc__ = (("Calculate Hessian with complex-step derivative "
                          "approximation\n") +
                          "\n".join(_hessian_docs.split("\n")[1:]) %
                          dict(scale="3", extra_params="",
                               extra_returns="", equation_number="10",
                               equation=("1/(2*d_j*d_k) * "
                                         "imag(f(x + i*d[j]*e[j] + "
                                         "d[k]*e[k]) -\n"
                                         "                     "
                                         "f(x + i*d[j]*e[j] - d[k]*e[k]))\n"))
                          )


def approx_hess1(x, f, epsilon=None, args=(), kwargs={}, return_grad=False):
    n = len(x)
    h = _get_epsilon(x, 3, epsilon, n)
    ee = np.diag(h)

    f0 = f(*((x,)+args), **kwargs)
    # Compute forward step
    g = np.zeros(n)
    for i in range(n):
        g[i] = f(*((x+ee[i, :],)+args), **kwargs)

    hess = np.outer(h, h)  # this is now epsilon**2
    # Compute "double" forward step
    for i in range(n):
        for j in range(i, n):
            hess[i, j] = (f(*((x + ee[i, :] + ee[j, :],) + args), **kwargs) -
                          g[i] - g[j] + f0)/hess[i, j]
            hess[j, i] = hess[i, j]
    if return_grad:
        grad = (g - f0)/h
        return hess, grad
    else:
        return hess

approx_hess1.__doc__ = _hessian_docs % dict(scale="3",
extra_params="""return_grad : bool
        Whether or not to also return the gradient
""",
extra_returns="""grad : nparray
        Gradient if return_grad == True
""",
equation_number="7",
equation="""1/(d_j*d_k) * ((f(x + d[j]*e[j] + d[k]*e[k]) - f(x + d[j]*e[j])))
""")


def approx_hess2(x, f, epsilon=None, args=(), kwargs={}, return_grad=False):
    #
    n = len(x)
    # NOTE: ridout suggesting using eps**(1/4)*theta
    h = _get_epsilon(x, 3, epsilon, n)
    ee = np.diag(h)
    f0 = f(*((x,)+args), **kwargs)
    # Compute forward step
    g = np.zeros(n)
    gg = np.zeros(n)
    for i in range(n):
        g[i] = f(*((x+ee[i, :],)+args), **kwargs)
        gg[i] = f(*((x-ee[i, :],)+args), **kwargs)

    hess = np.outer(h, h)  # this is now epsilon**2
    # Compute "double" forward step
    for i in range(n):
        for j in range(i, n):
            hess[i, j] = (f(*((x + ee[i, :] + ee[j, :],) + args), **kwargs) -
                          g[i] - g[j] + f0 +
                          f(*((x - ee[i, :] - ee[j, :],) + args), **kwargs) -
                          gg[i] - gg[j] + f0)/(2 * hess[i, j])
            hess[j, i] = hess[i, j]
    if return_grad:
        grad = (g - f0)/h
        return hess, grad
    else:
        return hess


approx_hess2.__doc__ = _hessian_docs % dict(scale="3",
extra_params="""return_grad : bool
        Whether or not to also return the gradient
""",
extra_returns="""grad : nparray
        Gradient if return_grad == True
""",
equation_number="8",
equation = """1/(2*d_j*d_k) * ((f(x + d[j]*e[j] + d[k]*e[k]) - f(x + d[j]*e[j])) -
                 (f(x + d[k]*e[k]) - f(x)) +
                 (f(x - d[j]*e[j] - d[k]*e[k]) - f(x + d[j]*e[j])) -
                 (f(x - d[k]*e[k]) - f(x)))
""")


def approx_hess3(x, f, epsilon=None, args=(), kwargs={}):
    n = len(x)
    h = _get_epsilon(x, 4, epsilon, n)
    ee = np.diag(h)
    hess = np.outer(h,h)

    for i in range(n):
        for j in range(i, n):
            hess[i, j] = (f(*((x + ee[i, :] + ee[j, :],) + args), **kwargs)
                          - f(*((x + ee[i, :] - ee[j, :],) + args), **kwargs)
                          - (f(*((x - ee[i, :] + ee[j, :],) + args), **kwargs)
                          - f(*((x - ee[i, :] - ee[j, :],) + args), **kwargs),)
                          )/(4.*hess[i, j])
            hess[j, i] = hess[i, j]
    return hess

approx_hess3.__doc__ = _hessian_docs % dict(scale="4", extra_params="",
                                            extra_returns="",
                                            equation_number="9",
equation = """1/(4*d_j*d_k) * ((f(x + d[j]*e[j] + d[k]*e[k]) - f(x + d[j]*e[j]
                                                     - d[k]*e[k])) -
                 (f(x - d[j]*e[j] + d[k]*e[k]) - f(x - d[j]*e[j]
                                                     - d[k]*e[k]))""")
approx_hess = approx_hess3
approx_hess.__doc__ += "\n    This is an alias for approx_hess3"


if __name__ == '__main__': #pragma : no cover
    import statsmodels.api as sm
    from scipy.optimize.optimize import approx_fhess_p
    import numpy as np

    data = sm.datasets.spector.load()
    data.exog = sm.add_constant(data.exog, prepend=False)
    mod = sm.Probit(data.endog, data.exog)
    res = mod.fit(method="newton")
    test_params = [1,0.25,1.4,-7]
    llf = mod.loglike
    score = mod.score
    hess = mod.hessian

    # below is Josef's scratch work

    def approx_hess_cs_old(x, func, args=(), h=1.0e-20, epsilon=1e-6):
        def grad(x):
            return approx_fprime_cs(x, func, args=args, h=1.0e-20)

        #Hessian from gradient:
        return (approx_fprime(x, grad, epsilon)
                + approx_fprime(x, grad, -epsilon))/2.


    def fun(beta, x):
        return np.dot(x, beta).sum(0)

    def fun1(beta, y, x):
        #print(beta.shape, x.shape)
        xb = np.dot(x, beta)
        return (y-xb)**2 #(xb-xb.mean(0))**2

    def fun2(beta, y, x):
        #print(beta.shape, x.shape)
        return fun1(beta, y, x).sum(0)

    nobs = 200
    x = np.arange(nobs*3).reshape(nobs,-1)
    x = np.random.randn(nobs,3)

    xk = np.array([1,2,3])
    xk = np.array([1.,1.,1.])
    #xk = np.zeros(3)
    beta = xk
    y = np.dot(x, beta) + 0.1*np.random.randn(nobs)
    xk = np.dot(np.linalg.pinv(x),y)


    epsilon = 1e-6
    args = (y,x)
    from scipy import optimize
    xfmin = optimize.fmin(fun2, (0,0,0), args)
    print(approx_fprime((1,2,3),fun,epsilon,x))
    jac = approx_fprime(xk,fun1,epsilon,args)
    jacmin = approx_fprime(xk,fun1,-epsilon,args)
    #print(jac)
    print(jac.sum(0))
    print('\nnp.dot(jac.T, jac)')
    print(np.dot(jac.T, jac))
    print('\n2*np.dot(x.T, x)')
    print(2*np.dot(x.T, x))
    jac2 = (jac+jacmin)/2.
    print(np.dot(jac2.T, jac2))

    #he = approx_hess(xk,fun2,epsilon,*args)
    print(approx_hess_old(xk,fun2,1e-3,args))
    he = approx_hess_old(xk,fun2,None,args)
    print('hessfd')
    print(he)
    print('epsilon =', None)
    print(he[0] - 2*np.dot(x.T, x))

    for eps in [1e-3,1e-4,1e-5,1e-6]:
        print('eps =', eps)
        print(approx_hess_old(xk,fun2,eps,args)[0] - 2*np.dot(x.T, x))

    hcs2 = approx_hess_cs(xk,fun2,args=args)
    print('hcs2')
    print(hcs2 - 2*np.dot(x.T, x))

    hfd3 = approx_hess(xk,fun2,args=args)
    print('hfd3')
    print(hfd3 - 2*np.dot(x.T, x))

    import numdifftools as nd
    hnd = nd.Hessian(lambda a: fun2(a, y, x))
    hessnd = hnd(xk)
    print('numdiff')
    print(hessnd - 2*np.dot(x.T, x))
    #assert_almost_equal(hessnd, he[0])
    gnd = nd.Gradient(lambda a: fun2(a, y, x))
    gradnd = gnd(xk)
