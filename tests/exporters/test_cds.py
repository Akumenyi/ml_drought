from src.exporters import CDSExporter


class TestCDSExporter:

    def test_filename_year(self):

        dataset = 'megadodo-publications'
        selection_request = {
            'year': [1979, 1978, 1980]
        }

        filename = CDSExporter.make_filename(dataset, selection_request)
        expected = 'megadodo-publications_1978_1980.nc'
        assert filename == expected, f'Got {filename}, expected {expected}!'

    def test_filename_date(self):
        dataset = 'megadodo-publications'
        selection_request = {
            'date': '1978-12-01/1980-12-31'
        }

        sanitized_date = selection_request["date"].replace('/', '_')
        filename = CDSExporter.make_filename(dataset, selection_request)
        expected = f'megadodo-publications_{sanitized_date}.nc'
        assert filename == expected, f'Got {filename}, expected {expected}!'
