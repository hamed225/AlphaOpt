"""
Custom objective GP model, time GP model, acquisition function, evaluator function
goes here
"""
import GPyOpt
from GPyOpt.acquisitions.base import AcquisitionBase
from GPyOpt.acquisitions.EI import AcquisitionEI
from GPyOpt.core.evaluators.base import EvaluatorBase
from GPyOpt.core.task.cost import CostModel
from GPyOpt.core.task.cost import constant_cost_withGradients
from GPyOpt.util.general import get_quantiles
from GPyOpt.optimization import optimizer
from GPyOpt.util.stats import initial_design
from GPyOpt.methods.modular_bayesian_optimization import ModularBayesianOptimization
import math
import numpy as np
from GPyOpt.models import GPModel


"""
Objective GP Model
"""



"""
Time GP Model
Re-implement GPyOpt.core.task.cost.CostModel
"""
class CustomCostModel(CostModel):
    def __init__(self, kernel, cost_withGradients):
        super(CustomCostModel,self).__init__(cost_withGradients)

        # --- Set-up evaluation cost
        if self.cost_type == None:
            self.cost_withGradients = CostModel.constant_cost_withGradients
            self.cost_type = 'Constant cost'

        elif self.cost_type == 'evaluation_time':
            self.cost_model = GPModel(kernel=kernel, exact_feval=False,
                                      normalize_Y=False, optimize_restarts=5)
            self.cost_withGradients = self._cost_gp_withGradients
            self.num_updates = 0
        else:
            self.cost_withGradients = cost_withGradients
            self.cost_type = 'Used defined cost'

    def get_model_parameters(self):
        """
        Returns a 2D numpy array with the parameters of the model
        """
        return np.atleast_2d(self.cost_model.get_model_parameters())


"""
Acquisition Function
"""  
#TODO: Still need to figure out correct sign for acquisition functions
class EIXplore(AcquisitionBase):
    """
    Usage: Cycle is a parameter deciding how often to explore. Cycle = 2 implies
    alternate between exploration and exploitation. Cycle = 3 implies explore
    once every 3 evaluations.
    """
    analytical_gradient_prediction = False
    
    jitter = 0
    
    explore = 0
    cycle = 3
    
    prev = None

    def __init__(self, model, space, optimizer, cost_withGradients=None, jitter=0.01, cycle=3):
        super(EIXplore, self).__init__(model, space, optimizer)

        self.jitter = jitter
        self.cycle = cycle
        if cost_withGradients == None:
             self.cost_withGradients = constant_cost_withGradients
        else:
             self.cost_withGradients = cost_withGradients 

    def _compute_acq(self,x):
        m, s = self.model.predict(x)
        fmin = self.model.get_fmin()
        phi, Phi, _ = get_quantiles(self.jitter, fmin, m, s)
        h = 0.5 * np.log(2*math.pi*math.e*np.square(s))
        if self.prev != None and abs(self.prev-fmin) < 1:
            self.prev = fmin
            return h
        
        self.prev = fmin
        f_acqu_x = h if (self.explore % self.cycle) == 0 else (fmin - m + self.jitter) * Phi + s * phi
        self.explore += 1
        self.explore %= self.cycle
        return f_acqu_x


class EntropyWeightedEI(AcquisitionBase):
    analytical_gradient_prediction = False

    def __init__(self, model, space, optimizer, cost_withGradients=None):
        super(EntropyWeightedEI, self).__init__(model, space, optimizer)
        
        self.EI = AcquisitionEI(model, space, optimizer, cost_withGradients)

        if cost_withGradients == None:
             self.cost_withGradients = constant_cost_withGradients
        else:
             self.cost_withGradients = cost_withGradients

    def _compute_acq(self,x):
        m, s = self.model.predict(x)
        acqu_x = self.EI.acquisition_function(x)
        
        h = 0.5 * np.log(2*math.pi*math.e*np.square(s))
        for i in range (acqu_x.shape[0]):
            acqu_x[i] += h[i]
        return acqu_x


# Meant to be used with posterior sampling
class EntropyExplore(AcquisitionBase):
    analytical_gradient_prediction = False

    def __init__(self, model, space, optimizer, cost_withGradients=None):
        super(EntropyExplore, self).__init__(model, space, optimizer)
        
        self.EI = AcquisitionEI(model, space, optimizer, cost_withGradients)

        if cost_withGradients == None:
             self.cost_withGradients = constant_cost_withGradients
        else:
             self.cost_withGradients = cost_withGradients 


    def _compute_acq(self,x):
        m, s = self.model.predict(x)
        h = 0.5 * np.log(2*math.pi*math.e*np.square(s))
        return h


class PITarget(AcquisitionBase):
    """
    Usage: Target is the target output value (optimum of the black-box function)
    that we want to hit. This is usually unknown except for test functions.
    However, in our experiments, the target would be the accuracy, so depending
    on the units, target = 100 or target = 1 (default)
    """
    analytical_gradient_prediction = True

    def __init__(self, model, space, optimizer=None, cost_withGradients=None, jitter=0.2, target=None):
        super(PITarget, self).__init__(model, space, optimizer, cost_withGradients=cost_withGradients)
        self.jitter = jitter
        self.target = 0 if target is None else target

    def _compute_acq(self, x):
        m, s = self.model.predict(x)
        fmin = self.target if self.target is not None else self.model.get_fmin()
        _, Phi, _ = get_quantiles(self.jitter, fmin, m, s)    
        f_acqu = Phi
        self.jitter *= .5
        return f_acqu

    def _compute_acq_withGradients(self, x):
        fmin = self.target if self.target is not None else self.model.get_fmin()
        m, s, dmdx, dsdx = self.model.predict_withGradients(x)
        phi, Phi, u = get_quantiles(self.jitter, fmin, m, s)    
        f_acqu = Phi
        df_acqu = -(phi/s)* (dmdx + dsdx * u)

        self.jitter *= .5
        return f_acqu, df_acqu


class RandomAcquisition(AcquisitionBase):
    """
    Use this for random search
    """

    def __init__(self, model, space, optimizer, cost_withGradients=None):
        super(RandomAcquisition, self).__init__(model, space, optimizer, cost_withGradients=None)

    def _compute_acq(self, x):
        return np.random.uniform()

    def _compute_acq_withGradients(self, x):
        return np.random.uniform()


class MultiAcquisitions(EvaluatorBase):
    """
    Usage: Pass in a list of acquisition functions that you want to be evaluated
    across all cores.

    See Parallel Modular BO.ipynb for an example.
    """
    def __init__(self, *args):
        self.acquisitions = args

    def compute_batch(self):
        X_batch = self.acquisitions[0].optimize()
        for i in range(1, len(self.acquisitions)):
            X_batch = np.vstack((X_batch, self.acquisitions[i].optimize()))
        return X_batch


# My BO
class MyModularBayesianOptimization(ModularBayesianOptimization):
    """
    ModularBayesianOptimization with cost parameter saving
    """
    def __init__(self, model, space, objective, acquisition, evaluator, X_init,
                 Y_init=None, cost=None, normalize_Y=True, model_update_interval=1):
        self.cost_parameters_iterations = None
        self.initial_design_numdata = len(X_init)
        super(MyModularBayesianOptimization, self).__init__(self, model, space, objective,
                                                            acquisition, evaluator, X_init,
                                                            Y_init=Y_init, cost=cost, normalize_Y=normalize_Y,
                                                            model_update_interval=model_update_interval)

    def _save_model_parameter_values(self):
        if self.model_parameters_iterations == None:
            self.model_parameters_iterations = self.model.get_model_parameters()
        else:
            self.model_parameters_iterations = np.vstack((self.model_parameters_iterations,
                                                          self.model.get_model_parameters()))
        if self.cost_parameters_iterations == None:
            self.cost_parameters_iterations = self.cost.get_model_parameters()
        else:
            self.cost_parameters_iterations = np.vstack(
                (self.cost_parameters_iterations, self.cost.get_model_parameters()))

