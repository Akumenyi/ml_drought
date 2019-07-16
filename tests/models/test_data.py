import torch
import numpy as np
import pytest
import xarray as xr
import pandas as pd

from src.models.data import DataLoader, _BaseIter, TrainData

from ..utils import _make_dataset


class TestBaseIter:

    def test_mask(self, tmp_path):

        for i in range(5):
            (
                tmp_path / f'features/one_month_forecast/train/{i}'
            ).mkdir(parents=True)
            (tmp_path / f'features/one_month_forecast/train/{i}/x.nc').touch()
            (tmp_path / f'features/one_month_forecast/train/{i}/y.nc').touch()

        mask_train = [True, True, False, True, False]
        mask_val = [False, False, True, False, True]

        train_paths = DataLoader._load_datasets(tmp_path, mode='train',
                                                experiment='one_month_forecast',
                                                shuffle_data=True,
                                                mask=mask_train)
        val_paths = DataLoader._load_datasets(tmp_path, mode='train',
                                              experiment='one_month_forecast',
                                              shuffle_data=True, mask=mask_val)
        assert len(set(train_paths).intersection(set(val_paths))) == 0, \
            f'Got the same file in both train and val set!'
        assert len(train_paths) + len(val_paths) == 5, f'Not all files loaded!'

    def test_pred_months(self, tmp_path):
        for i in range(1, 13):
            (tmp_path / f'features/one_month_forecast/train/2018_{i}').mkdir(parents=True)
            (tmp_path / f'features/one_month_forecast/train/2018_{i}/x.nc').touch()
            (tmp_path / f'features/one_month_forecast/train/2018_{i}/y.nc').touch()

        pred_months = [4, 5, 6]

        train_paths = DataLoader._load_datasets(tmp_path, mode='train',
                                                shuffle_data=True, pred_months=pred_months,
                                                experiment='one_month_forecast')

        assert len(train_paths) == len(pred_months), \
            f'Got {len(train_paths)} filepaths back, expected {len(pred_months)}'

        for return_file in train_paths:
            subfolder = return_file.parts[-1]
            month = int(str(subfolder)[5:])
            assert month in pred_months, f'{month} not in {pred_months}, got {return_file}'

    @pytest.mark.parametrize(
        'normalize,to_tensor,experiment,surrounding_pixels',
        [(True, True, 'one_month_forecast', 1),
         (True, False, 'one_month_forecast', None),
         (False, True, 'one_month_forecast', 1),
         (False, False, 'one_month_forecast', None),
         (True, True, 'nowcast', 1),
         (True, False, 'nowcast', None),
         (False, True, 'nowcast', 1),
         (False, False, 'nowcast', None)]
    )
    def test_ds_to_np(self, tmp_path, normalize, to_tensor, experiment, surrounding_pixels):

        x_pred, _, _ = _make_dataset(size=(5, 5))
        x_coeff, _, _ = _make_dataset(size=(5, 5), variable_name='precip')
        x = xr.merge([x_pred, x_coeff])
        y = x_pred.isel(time=[0])

        data_dir = (tmp_path / experiment)
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)

        x.to_netcdf(data_dir / 'x.nc')
        y.to_netcdf(data_dir / 'y.nc')

        norm_dict = {}
        for var in x.data_vars:
            norm_dict[var] = {
                'mean': x[var].mean(dim=['lat', 'lon'], skipna=True).values,
                'std': x[var].std(dim=['lat', 'lon'], skipna=True).values
            }

        class MockLoader:
            def __init__(self):
                self.batch_file_size = None
                self.mode = None
                self.shuffle = None
                self.clear_nans = None
                self.data_files = []
                self.normalizing_dict = norm_dict if normalize else None
                self.to_tensor = None
                self.experiment = experiment
                self.surrounding_pixels = surrounding_pixels

        base_iterator = _BaseIter(MockLoader())

        arrays = base_iterator.ds_folder_to_np(data_dir, return_latlons=True,
                                               to_tensor=to_tensor)

        x_train_data, y_np, latlons = (
            arrays.x, arrays.y, arrays.latlons
        )
        assert isinstance(x_train_data, TrainData)
        if not to_tensor:
            assert isinstance(y_np, np.ndarray)

        if to_tensor:
            assert (
                type(x_train_data.historical) == torch.Tensor
            ) and (type(y_np) == torch.Tensor)
        else:
            assert (
                type(x_train_data.historical) == np.ndarray
            ) and (type(y_np) == np.ndarray)

        if (not normalize) and (experiment == 'nowcast') and (not to_tensor):
            assert (
                x_train_data.historical.shape[0] == x_train_data.current.shape[0]
            ), "The 0th dimension (latlons) should be equal in the " \
                f"historical ({x_train_data.historical.shape[0]}) and " \
                f"current ({x_train_data.current.shape[0]}) arrays."

            expected = (
                x.precip
                .sel(time=y.time)
                .stack(dims=['lat', 'lon'])
                .values.T
            )
            got = x_train_data.current
            if surrounding_pixels is None:
                assert expected.shape == got.shape, "should have stacked latlon" \
                    " vars as the first dimension in the current array."

                assert all(expected == got), "" \
                    "Expected to find the target timesetep of `precip` values"\
                    "(the non-target variable for the target timestep: " \
                    f"({pd.to_datetime(y.time.values).strftime('%Y-%m-%d')[0]})." \
                    f"Expected: {expected[:5]}. Got: {got[:5]}"

        if normalize and (experiment == 'nowcast') and (not to_tensor):
            assert x_train_data.current.max() < 6, f"The current data should be" \
                f" normalized. Currently: {x_train_data.current.flatten()}"

        for idx in range(latlons.shape[0]):
            lat, lon = latlons[idx, 0], latlons[idx, 1]
            for time in range(x_train_data.historical.shape[1]):
                target = x.isel(time=time).sel(lat=lat).sel(lon=lon).VHI.values

                if (not normalize) and (not to_tensor):
                    assert target == x_train_data.historical[idx, time, 0], \
                        'Got different x values for time idx:'\
                        f'{time}, lat: {lat}, lon: {lon} Expected {target}, '\
                        f'got {x_train_data.historical[idx, time, 0]}'

    @pytest.mark.parametrize('normalize', [True, False])
    def test_ds_to_np_multi_vars(self, tmp_path, normalize):
        to_tensor, experiment = False, 'nowcast'

        x_pred, _, _ = _make_dataset(size=(5, 5))
        x_coeff1, _, _ = _make_dataset(size=(5, 5), variable_name='precip')
        x_coeff2, _, _ = _make_dataset(size=(5, 5), variable_name='soil_moisture')
        x_coeff3, _, _ = _make_dataset(size=(5, 5), variable_name='temp')
        x = xr.merge([x_pred, x_coeff1, x_coeff2, x_coeff3])
        y = x_pred.isel(time=[0])

        data_dir = (tmp_path / experiment)
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)

        x.to_netcdf(data_dir / 'x.nc')
        y.to_netcdf(data_dir / 'y.nc')

        norm_dict = {}
        for var in x.data_vars:
            norm_dict[var] = {
                'mean': x[var].mean(dim=['lat', 'lon'], skipna=True).values,
                'std': x[var].std(dim=['lat', 'lon'], skipna=True).values
            }

        class MockLoader:
            def __init__(self):
                self.batch_file_size = None
                self.mode = None
                self.shuffle = None
                self.clear_nans = None
                self.data_files = []
                self.normalizing_dict = norm_dict if normalize else None
                self.to_tensor = None
                self.experiment = experiment
                self.surrounding_pixels = None

        base_iterator = _BaseIter(MockLoader())

        arrays = base_iterator.ds_folder_to_np(data_dir, return_latlons=True,
                                               to_tensor=to_tensor)

        x_train_data, _, latlons = (
            arrays.x, arrays.y, arrays.latlons
        )
        assert x_train_data.historical.shape[-1] == 4, "There should be" \
            "4 historical variables (the final dimension):" \
            f"{x_train_data.historical.shape}"

        assert x_train_data.current.shape == (25, 3), "Expecting multiple vars" \
            "in the current timestep. Expect: (25, 3) "\
            f"Got: {x_train_data.current.shape}"

        assert latlons.shape == (25, 2), "The shape of latlons should not change"\
            f"Got: {latlons.shape}. Expecting: (25, 2)"

        if not normalize:
            # test that we are getting the right `current` data
            relevant_features = ['precip', 'soil_moisture', 'temp']
            target_time = y.time
            expected = (
                x[relevant_features]   # all vars except target_var
                .sel(time=target_time)  # select the target_time
                .stack(dims=['lat', 'lon'])  # stack lat,lon so shape = (lat*lon, time, dims)
                .to_array().values[:, 0, :].T  # extract numpy array, transpose and drop dim
            )

            assert np.all(x_train_data.current == expected), f"Expected to " \
                "find the target_time data for the non target variables"

    def test_surrounding_pixels(self):
        x, _, _ = _make_dataset(size=(10, 10))
        org_vars = list(x.data_vars)

        x_with_more = _BaseIter._add_surrounding(x, 1)
        shifted_vars = x_with_more.data_vars

        for data_var in org_vars:
            for lat in [-1, 0, 1]:
                for lon in [-1, 0, 1]:
                    if lat == lon == 0:
                        assert f'lat_{lat}_lon_{lon}_{data_var}' not in shifted_vars, \
                            f'lat_{lat}_lon_{lon}_{data_var} should not ' \
                            f'be in the shifted variables'
                    else:
                        shifted_var_name = f'lat_{lat}_lon_{lon}_{data_var}'
                        assert shifted_var_name in shifted_vars, \
                            f'{shifted_var_name} is not in the shifted variables'

                        org = x_with_more.VHI.isel(time=0, lon=5, lat=5).values
                        shifted = x_with_more[shifted_var_name].isel(time=0,
                                                                     lon=5 + lon,
                                                                     lat=5 + lat).values
                        assert org == shifted, f"Shifted values don't match!"
