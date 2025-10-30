import logging

import numpy as np
import pandas as pd
from pandas import DataFrame
from timebudget import timebudget

from .df import DF
from .standings import Standings


class TeamRatings(DF):
    def __init__(self, d: DataFrame = DataFrame()):
        super().__init__(d, "team_ratings")

    @staticmethod
    def _calc_rating(points: int, gd: int):
        return points + gd

    @staticmethod
    def _get_season_weightings(no_seasons: int):
        mult = 2.5  # High = recent weighted more
        season_weights = [0.01 * (mult**3), 0.01 * (mult**2), 0.01 * mult, 0.01]
        weights = np.array(season_weights[:no_seasons])
        return list(weights / sum(weights))  # Normalise list

    def _calc_total_rating_col(
        self,
        team_ratings: dict,
        no_seasons: int,
        include_current_season: bool,
    ):
        # Calculate total rating column
        team_ratings["total"] = 0
        if include_current_season:
            start_n = 0  # Include current season when calculating total rating
            w = self._get_season_weightings(no_seasons)  # Column weights
        else:
            start_n = 1  # Exclude current season when calculating total rating
            w = self._get_season_weightings(no_seasons - 1)  # Column weights

        for n in range(start_n, no_seasons):
            team_ratings["total"] += (
                w[n - start_n] * team_ratings[f"prevSeason{n}"]
            )

    @staticmethod
    def init_rating_columns(team_ratings: DataFrame, num_seasons: int):
        # Create column for each included season
        for n in range(0, num_seasons):
            team_ratings[f"prevSeason{n}"] = np.nan

    def insert_rating_values(
        self,
        team_ratings: DataFrame,
        standings: Standings,
        current_season: int,
        num_seasons: int,
    ):
        for team, row in standings.df.iterrows():
            for n in range(num_seasons):
                rating = self._calc_rating(
                    row[current_season - n]["points"], row[current_season - n]["gD"]
                )
                team_ratings.at[team, f"prevSeason{n}"] = rating

    @staticmethod
    def replace_nan(team_ratings: DataFrame):
        # Replace any NaN with the lowest rating in the same column
        for col in team_ratings.columns:
            team_ratings[col] = team_ratings[col].replace(
                np.nan, team_ratings[col].min()
            )

    @staticmethod
    def normalise_ratings(team_ratings: DataFrame, num_seasons: int):
        # Create normalised versions of the three ratings columns
        for n in range(0, num_seasons):
            col_heading = f"prevSeason{n}"
            team_ratings[col_heading] = (
                team_ratings[col_heading] - team_ratings[col_heading].min()
            ) / (
                team_ratings[col_heading].max()
                - team_ratings[col_heading].min()
            )

    @staticmethod
    def include_current_season(
        standings: Standings, current_season: int, games_threshold: float
    ):
        """Check whether current season data should be included in each team's total rating
        If current season hasn't played enough games, don't include.
        """
        if (standings.df[current_season]["played"] <= games_threshold).all():
            logging.info(
                f"Team Ratings: Current season excluded from calculation; all teams must have played {games_threshold} games."
            )
            return False
        return True

    @staticmethod
    def clean_dataframe(team_ratings: DataFrame):
        team_ratings = team_ratings.sort_values(by="total", ascending=False)
        team_ratings = team_ratings.rename(columns={"prevSeason0": "current"})
        return team_ratings

    @timebudget
    def build(
        self,
        standings: Standings,
        season: int,
        games_threshold: int,
        num_seasons: int = 3,
        display: bool = False,
    ):
        """ Assigns self.df a DataFrame containing each team's calculated
            'team rating' based on the last [num_seasons] seasons results.

            Rows: the 20 teams participating in the current season, ordered
                descending by the team's rating
            Columns (multi-index):
            -----------------------------------
            | current | prevSeason[N] | total |

            current: a normalised value that represents the team's rating
                based on the state of the current season's standings table.
            prevSeason[N]: a normalised value that represents the team's rating
                based on the state of the standings table [N] seasons ago.
            total: a final normalised rating value incorporating the values
                from all normalised columns.

        Args:
            standings Standings: a completed DataFrame filled with standings data
                for the last num_seasons seasons
            season int: the year of the current season
            games_threshold: the minimum number of home games all teams must have
                played in any given season for the home advantage calculated for
                each team during that season to be incorporated into the total home
                advantage value
            num_seasons (int, optional): number of seasons to include. Defaults to 3.
            display (bool, optional): flag to print the DataFrame to console after
                creation. Defaults to False.
        """
        self.log_building(season)
        self._check_dependencies(standings)

        # Add current season team names to the object team DataFrame
        team_ratings = pd.DataFrame(index=standings.df.index)

        self.init_rating_columns(team_ratings, num_seasons)
        self.insert_rating_values(team_ratings, standings, season, num_seasons)
        self.replace_nan(team_ratings)
        self.normalise_ratings(team_ratings, num_seasons)
        include_cs = self.include_current_season(standings, season, games_threshold)
        self._calc_total_rating_col(team_ratings, num_seasons, include_cs)

        team_ratings = self.clean_dataframe(team_ratings)

        if display:
            print(team_ratings)

        self.df = team_ratings
