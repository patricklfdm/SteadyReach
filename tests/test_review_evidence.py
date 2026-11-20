from unittest import TestCase
from ras_workflow.review_evidence import rating


class RatingTests(TestCase):
    sample=b'# //STATION AGENCY="USGS " NUMBER="11160000 "\n# //RATING_INDEP PARAMETER="Gage height (ft)"\n# //RATING_DEP PARAMETER="Discharge (ft^3/s)"\n# //RATING_DATETIME BEGIN=20240101 END=----\nINDEP\tSHIFT\tDEP\tSTOR\n16N\t16N\t16N\t1S\n1.1\t0\t10\t\n1.3\t0\t20\t\n'
    def test_preserves_validity_and_flags_out_of_range(self):
        result=rating(self.sample,'11160000',{'A':12,'B':30})
        self.assertEqual(result['profile_in_range'],{'A':True,'B':False})
        self.assertEqual(len(result['validity']),1)

    def test_rejects_another_gage_or_unknown_units(self):
        for raw,station in [(self.sample,'03311222'),(self.sample.replace(b'Discharge (ft^3/s)',b'Discharge (m3/s)'),'11160000')]:
            with self.assertRaises(ValueError):rating(raw,station,{'A':10})
