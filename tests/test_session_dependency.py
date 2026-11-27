import unittest
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.dependencies import get_session, get_session_factory
from backend.app.main import create_app


class SessionDependencyTests(unittest.TestCase):
    def test_closes_session_on_success_and_failure(self):
        session = MagicMock()
        factory = MagicMock()
        factory.return_value.__enter__.return_value = session
        app = FastAPI()
        app.dependency_overrides[get_session_factory] = lambda: factory

        @app.get('/{fail}')
        def endpoint(fail: bool, db=Depends(get_session)):
            self.assertIs(db, session)
            if fail:
                raise HTTPException(status_code=400)
            return {'ok': True}

        client = TestClient(app)
        self.assertEqual(client.get('/false').status_code, 200)
        self.assertEqual(client.get('/true').status_code, 400)
        self.assertEqual(factory.return_value.__exit__.call_count, 2)
        self.assertIsNone(factory.return_value.__exit__.call_args_list[0].args[0])
        self.assertIs(factory.return_value.__exit__.call_args_list[1].args[0], HTTPException)

    def test_override_reaches_real_router(self):
        app = create_app()
        session = MagicMock()
        app.dependency_overrides[get_session] = lambda: session
        with patch('backend.app.routers.public.PublicActivityRepository') as repository, \
             patch('backend.app.routers.public.recent_listened_albums', return_value=[]):
            response = TestClient(app).get('/api/public/recent-listens')
        self.assertEqual(response.status_code, 200)
        repository.assert_called_once_with(session)



if __name__ == '__main__':
    unittest.main()
